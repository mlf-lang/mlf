"""Executable pure sequential group-RC semantics, separate from the checker.

No dependency-order graph, reachability traversal or cycle discovery exists here.
All traversal on reclamation is of one known zero-count group's member slots.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from collections import deque
from typing import Any

from .checker import CheckedProgram, check


class RuntimeFault(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code, self.message = code, message
        super().__init__(f"{code}: {message}")


@dataclass
class Group:
    identity: int
    count: int = 0
    members: set[int] = field(default_factory=set)


@dataclass
class Node:
    identity: int
    group: int
    layout: str
    state: str
    slots: dict[str, int] = field(default_factory=dict)
    code: str | None = None
    token_slots: dict[str, int] = field(default_factory=dict)
    spent: bool = False
    scalar: int | bool | None = None
    variant: str | None = None


@dataclass
class Handle:
    identity: int
    group: int
    node: int | None = None
    own: bool = True
    anchor: int | None = None
    loans: int = 0
    token: int | None = None
    role: str = "owner"


class _Machine:
    def __init__(self, checked: CheckedProgram, fuel: int, event_limit: int):
        self.program = checked.data()
        self.checked = checked
        self.groups: dict[int, Group] = {}
        self.nodes: dict[int, Node] = {}
        self.handles: dict[int, Handle] = {}
        self.tokens: dict[int, tuple] = {}  # live affine permission custody, not historic tokens
        self.next_group = self.next_node = self.next_handle = 0
        self.next_observation_frame = 0
        self.owner_handles = 0
        self.fuel = fuel
        self.event_limit = event_limit
        self.events: list[dict] = []
        self.events_omitted = 0
        self.depth = 0
        self.result: dict | None = None
        self.closing: deque[int] = deque()
        self.in_close = False
        self.metrics = {key: 0 for key in (
            "steps", "groups_allocated", "groups_closed", "peak_groups", "nodes_allocated",
            "nodes_freed", "peak_nodes", "peak_owner_handles", "force_calls", "max_force_depth",
            "callback_calls", "raw_deferred_returns", "memo_writes", "internal_memo_slots",
            "cross_group_memo_slots", "memo_fast_paths", "loop_iterations",
            "max_loop_boundary_groups", "max_loop_boundary_nodes",
            "ordinary_calls", "repeat_calls", "once_calls", "applications_allocated",
            "tokens_created", "tokens_invoked", "tokens_discarded", "peak_live_tokens",
            "rc_inc_total", "rc_dec_total", "owner_handle_acquisitions", "owner_handle_releases",
            "loan_handle_acquisitions", "loan_handle_releases", "borrowed_slot_publications",
            "ir_retain_ops", "ir_drop_ops", "ir_borrow_ops", "ir_end_borrow_ops", "ir_application_borrow_ops",
            "groups_closed_during_force",
        )}
        for category in ("owner", "builder", "pin", "key", "slot"):
            self.metrics["rc_inc_" + category] = 0
            self.metrics["rc_dec_" + category] = 0

    def signature(self, shape: str) -> dict | None:
        signatures = self.program.get("signatures", {})
        return signatures.get(shape[1:]) if shape.startswith("@") else None

    def once(self, shape: str) -> bool:
        signature = self.signature(shape)
        return signature is not None and signature["protocol"] == "once"

    def event(self, event_name: str, **attributes: Any) -> None:
        if len(self.events) < self.event_limit:
            self.events.append({"event": event_name, **attributes})
        elif self.event_limit:
            self.events_omitted += 1

    def observing(self) -> bool:
        return len(self.events) < self.event_limit

    def slot_event(self, kind: str, host: Node, field: str, target: Node, *, reason: str) -> None:
        """Observe this actual slot operation, never discover graph reachability."""
        self.event(kind, host=host.identity, host_group=host.group, host_layout=host.layout,
                   field=field, target=target.identity, target_group=target.group,
                   target_layout=target.layout, target_state=target.state,
                   internal=host.group == target.group, reason=reason)

    def tick(self) -> None:
        self.metrics["steps"] += 1
        if self.metrics["steps"] > self.fuel:
            raise RuntimeFault("FUEL", "execution budget exhausted; no termination/cleanup claim")

    def peak(self) -> None:
        self.metrics["peak_groups"] = max(self.metrics["peak_groups"], len(self.groups))
        self.metrics["peak_nodes"] = max(self.metrics["peak_nodes"], len(self.nodes))
        self.metrics["peak_owner_handles"] = max(self.metrics["peak_owner_handles"], self.owner_handles)
        self.metrics["peak_live_tokens"] = max(self.metrics["peak_live_tokens"], len(self.tokens))

    def mint_token(self, handle: Handle) -> None:
        node = self.node(handle)
        if not self.once(node.layout) or node.identity in self.tokens or node.spent:
            raise RuntimeFault("INVARIANT", "Once permission may only be created with a fresh closure")
        handle.token = node.identity
        self.tokens[node.identity] = ("handle", handle.identity)
        self.metrics["tokens_created"] += 1
        self.peak()

    def retire_token(self, token: int, *, invoked: bool = False) -> None:
        if token not in self.tokens or token not in self.nodes or self.nodes[token].spent:
            raise RuntimeFault("INVARIANT", "Once permission was duplicated, spent or lost")
        del self.tokens[token]
        self.nodes[token].spent = True
        self.metrics["tokens_invoked" if invoked else "tokens_discarded"] += 1

    def acquire(self, node: Node) -> Handle:
        if self.once(node.layout):
            raise RuntimeFault("INVARIANT", "memory retain cannot duplicate Once call permission")
        return self.handle(node.group, node.identity)

    def take_slot(self, host: Node, field: str) -> Handle:
        target = self.nodes[host.slots[field]]
        if not self.once(target.layout):
            return self.acquire(target)
        token = host.token_slots.pop(field, None)
        if token is None or self.tokens.get(token) != ("slot", host.identity, field):
            raise RuntimeFault("INVARIANT", "Once slot does not own its permission")
        result = self.handle(target.group, target.identity)
        result.token = token
        self.tokens[token] = ("handle", result.identity)
        self.event("token_move", token=token, source="slot", destination=result.identity)
        return result

    def inc(self, group: int, *, reason: str) -> None:
        if group not in self.groups:
            raise RuntimeFault("INVARIANT", "attempted to resurrect a closed group")
        self.groups[group].count += 1
        self.metrics["rc_inc_total"] += 1
        self.metrics["rc_inc_" + reason] += 1

    def dec(self, group: int, *, reason: str) -> None:
        if group not in self.groups or self.groups[group].count <= 0:
            raise RuntimeFault("INVARIANT", "count underflow")
        self.groups[group].count -= 1
        self.metrics["rc_dec_total"] += 1
        self.metrics["rc_dec_" + reason] += 1
        if self.groups[group].count == 0:
            self.closing.append(group)
        if self.in_close:
            return
        self.in_close = True
        try:
            while self.closing:
                identity = self.closing.popleft()
                dead = self.groups[identity]
                if dead.count != 0:
                    raise RuntimeFault("INVARIANT", "zero-count group was resurrected")
                # Diagnostic-only inspection of this already-zero group's known
                # slots. This is not a reachability/cycle/admission traversal.
                internal_slots = cross_slots = None
                if self.observing():
                    internal_slots = cross_slots = 0
                    for member in dead.members:
                        for target_id in self.nodes[member].slots.values():
                            if self.nodes[target_id].group == identity:
                                internal_slots += 1
                            else:
                                cross_slots += 1
                self.event("close_group", group=identity, members=len(dead.members),
                           force_depth=self.depth, live_groups_before=len(self.groups),
                           internal_slots=internal_slots, cross_slots=cross_slots)
                if self.depth:
                    self.metrics["groups_closed_during_force"] += 1
                # Only the members and outgoing slots of this known dead group.
                for member in list(dead.members):
                    node = self.nodes[member]
                    for token in node.token_slots.values():
                        self.retire_token(token)
                    node.token_slots.clear()
                    for field, target_id in list(node.slots.items()):
                        target = self.nodes[target_id]
                        self.slot_event("slot_remove", node, field, target, reason="group_close")
                        if target.group != identity:
                            self.dec(target.group, reason="slot")
                    node.slots.clear()
                for member in dead.members:
                    del self.nodes[member]
                    self.metrics["nodes_freed"] += 1
                del self.groups[identity]
                self.metrics["groups_closed"] += 1
        finally:
            self.in_close = False

    def handle(self, group: int, node: int | None = None, *, anchor: Handle | None = None,
               role: str | None = None) -> Handle:
        if group not in self.groups or (node is not None and node not in self.nodes):
            raise RuntimeFault("INVARIANT", "handle to dead storage")
        self.next_handle += 1
        result = Handle(self.next_handle, group, node, anchor is None,
                        anchor.identity if anchor is not None else None)
        result.role = role or ("owner" if node is not None else "key")
        if result.own:
            self.inc(group, reason=result.role)
            self.owner_handles += 1
            self.metrics["owner_handle_acquisitions"] += 1
        else:
            self.live(anchor)
            if not anchor.own:
                raise RuntimeFault("INVARIANT", "a loan must have an exact owning anchor")
            anchor.loans += 1
            self.metrics["loan_handle_acquisitions"] += 1
        self.handles[result.identity] = result
        self.peak()
        return result

    def live(self, handle: Handle) -> Handle:
        if handle.identity not in self.handles or handle.group not in self.groups:
            raise RuntimeFault("INVARIANT", "use of dead handle")
        if not handle.own and handle.anchor not in self.handles:
            raise RuntimeFault("INVARIANT", "use of loan after exact anchor ended")
        return handle

    def drop(self, handle: Handle) -> None:
        self.live(handle)
        if handle.loans:
            raise RuntimeFault("INVARIANT", "dropping exact anchor with live loans")
        if not handle.own:
            self.handles[handle.anchor].loans -= 1
            self.metrics["loan_handle_releases"] += 1
        if handle.token is not None:
            if self.tokens.get(handle.token) != ("handle", handle.identity):
                raise RuntimeFault("INVARIANT", "handle lacks its claimed Once permission")
            self.retire_token(handle.token)
            handle.token = None
        del self.handles[handle.identity]
        if handle.own:
            self.owner_handles -= 1
            self.metrics["owner_handle_releases"] += 1
            self.dec(handle.group, reason=handle.role)

    def new_group(self) -> Handle:
        self.next_group += 1
        identity = self.next_group
        self.groups[identity] = Group(identity)
        self.metrics["groups_allocated"] += 1
        result = self.handle(identity, role="builder")
        self.event("new_group", group=identity)
        return result

    def node(self, handle: Handle) -> Node:
        self.live(handle)
        if handle.node is None:
            raise RuntimeFault("INVARIANT", "expected object reference")
        return self.nodes[handle.node]

    def slot(self, host: Node, field: str, target: Node, *, allow_once: bool = False) -> None:
        if field in host.slots:
            raise RuntimeFault("INVARIANT", "slot overwrite without discharge")
        if self.once(target.layout) and not allow_once:
            raise RuntimeFault("INVARIANT", "shared slot cannot duplicate Once permission")
        if host.group != target.group:
            self.inc(target.group, reason="slot")
        host.slots[field] = target.identity
        self.slot_event("slot_install", host, field, target, reason="publication")

    def store_handle(self, host: Node, field: str, source: Handle) -> None:
        target = self.node(source)
        self.slot(host, field, target, allow_once=True)
        if self.once(target.layout):
            token = source.token
            if token is None or self.tokens.get(token) != ("handle", source.identity):
                raise RuntimeFault("INVARIANT", "moved Once operand lacks its permission")
            source.token = None
            host.token_slots[field] = token
            self.tokens[token] = ("slot", host.identity, field)
            self.event("token_move", token=token, source=source.identity, destination="slot", host=host.identity, field=field)

    def clear_slots(self, node: Node) -> None:
        for token in node.token_slots.values():
            self.retire_token(token)
        node.token_slots.clear()
        targets = list(node.slots.items())
        node.slots.clear()
        for field, identity in targets:
            target = self.nodes[identity]
            self.slot_event("slot_remove", node, field, target, reason="payload_clear")
            if target.group != node.group:
                self.dec(target.group, reason="slot")

    def allocate(self, authority: Handle, layout: str, state: str,
                 fields: dict[str, Handle], code: str | None = None, *, move_tokens: bool = False,
                 source_out: str | None = None, frame_id: int | None = None, opcode: str | None = None) -> Handle:
        self.live(authority)
        self.next_node += 1
        node = Node(self.next_node, authority.group, layout, state, code=code)
        self.nodes[node.identity] = node
        self.groups[node.group].members.add(node.identity)
        for field, target in fields.items():
            if move_tokens:
                self.store_handle(node, field, target)
            else:
                self.slot(node, field, self.node(target))
        self.metrics["nodes_allocated"] += 1
        result = self.handle(node.group, node.identity)
        if state == "CLOSURE" and self.once(layout):
            self.mint_token(result)
        self.event("allocate", node=node.identity, group=node.group, state=state, code=code,
                   layout=layout, slots=dict(node.slots) if self.observing() else None,
                   out=source_out, frame=frame_id, opcode=opcode)
        return result

    def ready_scalar(self, handle: Handle, layout: str) -> int | bool:
        self.live(handle)
        node = self.node(handle)
        if not handle.own or node.state != 'READY' or node.layout != layout or node.code or node.slots:
            raise RuntimeFault('INVARIANT', 'scalar payload requires an owned ready exact intrinsic node')
        if layout == '#i64':
            valid = type(node.scalar) is int and -(1 << 63) <= node.scalar < (1 << 63)
        else:
            valid = layout == '#bool' and type(node.scalar) is bool
        if not valid:
            raise RuntimeFault('INVARIANT', 'scalar node has invalid payload')
        return node.scalar

    def variant_fields(self, family: str, variant: str) -> list[str]:
        return self.program['families'][family].get('fields', {}).get(variant, [])

    def sum_tag(self, handle: Handle, family: str) -> str:
        self.live(handle); node = self.node(handle)
        families = self.program.get('families', {})
        if family not in families or not handle.own or node.layout != '%' + family or node.state != 'READY' or node.code:
            raise RuntimeFault('INVARIANT', 'sum discriminator requires an owned ready exact-family node')
        if node.variant not in families[family]['variants']:
            raise RuntimeFault('INVARIANT', 'sum variant is not registered in the exact family')
        if len(node.slots) != len(self.variant_fields(family, node.variant)):
            raise RuntimeFault('INVARIANT', 'sum payload arity differs from variant')
        return node.variant

    def ready_sum(self, handle: Handle, family: str) -> str:
        variant = self.sum_tag(handle, family); node = self.node(handle)
        fields = self.variant_fields(family, variant)
        if list(node.slots) != [str(i) for i in range(len(fields))]:
            raise RuntimeFault('INVARIANT', 'sum payload positions not in declared order')
        for index, shape in enumerate(fields):
            if self.nodes[node.slots[str(index)]].layout != shape:
                raise RuntimeFault('INVARIANT', 'sum payload field shape differs')
        return variant

    def validate_sum_cursor(self, handle: Handle) -> None:
        node = self.node(handle)
        if node.layout.startswith('%'):
            family = node.layout[1:]
            if family not in self.program.get('families', {}):
                raise RuntimeFault('INVARIANT', 'sum cursor has unregistered nominal family')
            if node.state == 'READY': self.sum_tag(handle, family)
            elif node.state == 'CLOSURE':
                raise RuntimeFault('INVARIANT', 'nominal sum cannot carry callable closure state')

    def invoke(self, callee: Handle, argument: Handle, ceiling: Handle, *, parent_frame: int | None = None) -> Handle:
        """Consume owned callee/argument; return raw owned result at caller ceiling."""
        node = self.node(callee)
        if node.state != "CLOSURE":
            raise RuntimeFault("INVARIANT", "ordinary invocation needs a ready closure")
        spec = self.program["functions"][node.code]
        signature = self.program["signatures"][spec["signature"]]
        input_identity, input_token = argument.node, argument.token
        self.live(ceiling)
        pin = self.handle(ceiling.group, role="pin")
        home = self.handle(ceiling.group, anchor=pin)
        self.metrics["ordinary_calls"] += 1
        is_once = signature["protocol"] == "once"
        self.metrics["once_calls" if is_once else "repeat_calls"] += 1
        if is_once:
            if callee.token is None or self.tokens.get(callee.token) != ("handle", callee.identity):
                raise RuntimeFault("INVARIANT", "Once invocation needs the unique live call permission")
            self.retire_token(callee.token, invoked=True)
            callee.token = None
            captures = {name: self.take_slot(node, name) for name in list(node.slots)}
            self.event("closure_capture_handoff", node=node.identity, protocol="once",
                       owners={name: h.identity for name, h in captures.items()})
            self.clear_slots(node)
            self.event("closure_payload_cleared", node=node.identity)
        else:
            captures = {name: self.acquire(self.nodes[target]) for name, target in node.slots.items()}
            self.event("closure_capture_handoff", node=node.identity, protocol="repeat",
                       owners={name: h.identity for name, h in captures.items()})
        frame = {"$home": home, **captures, spec["parameter"]: argument}
        self.event("invoke_enter", closure=node.identity, closure_group=node.group, home=ceiling.group,
                   argument=argument.node, protocol=signature["protocol"])
        result = self.block(spec["body"], frame, parent_frame=parent_frame,
                            context={"kind": "function", "name": node.code, "node": node.identity,
                                     "home_group": ceiling.group})
        if result is None:
            raise RuntimeFault("INVARIANT", "function returned no owning result")
        self.live(result)
        if signature["result_identity"] == "argument" and (result.node != input_identity or result.token != input_token):
            raise RuntimeFault("INVARIANT", "checked identity summary disagrees with actual object/token return")
        self.event("invoke_raw_return", closure=node.identity, argument=input_identity, result=result.node,
                   token=result.token, owner=result.identity, home=ceiling.group)
        self.drop(home)
        self.drop(callee)
        self.drop(pin)
        return result

    def callback(self, node: Node, pin: Handle, captures: dict[str, Handle], *, parent_frame: int | None = None) -> Handle:
        spec = self.program["codes"][node.code]
        home = self.handle(node.group, anchor=pin)
        frame = {"$home": home, **captures}
        self.metrics["callback_calls"] += 1
        self.event("callback_enter", node=node.identity, pin=pin.identity)
        result = self.block(spec["body"], frame, parent_frame=parent_frame,
                            context={"kind": "thunk", "name": node.code, "node": node.identity,
                                     "home_group": node.group})
        if result is None:
            raise RuntimeFault("INVARIANT", "callback did not transfer an owner")
        self.live(result)
        result_node = self.node(result)
        self.event("raw_return", source=node.identity, result=result_node.identity,
                   result_state=result_node.state, owner=result.identity, home_pin=pin.identity)
        if result_node.state not in ("READY", "CLOSURE"):
            self.metrics["raw_deferred_returns"] += 1
        # The output owner is already real before activation custody ends.
        self.drop(home)
        return result

    def force(self, cursor: Handle, *, parent_frame: int | None = None) -> Handle:
        expected_layout = self.node(cursor).layout
        self.validate_sum_cursor(cursor)
        self.metrics["force_calls"] += 1
        self.depth += 1
        self.metrics["max_force_depth"] = max(self.metrics["max_force_depth"], self.depth)
        pending: list[tuple[Node, Handle]] = []  # private per invocation
        self.event("force_enter", depth=self.depth, cursor=cursor.node)
        try:
            while True:
                self.tick()
                node = self.node(cursor)
                if expected_layout.startswith('%') and node.layout != expected_layout:
                    raise RuntimeFault('INVARIANT', 'sum Force cursor crossed a nominal family')
                self.validate_sum_cursor(cursor)
                if node.state in ("READY", "CLOSURE"):
                    break
                if node.state in ("HOLE", "BUSY"):
                    raise RuntimeFault(node.state, "terminal pure-machine failure; recovery is unsupported")
                if node.state == "MEMO":
                    target = self.nodes[node.slots["$target"]]
                    next_cursor = self.acquire(target)
                    self.metrics["memo_fast_paths"] += 1
                    self.drop(cursor)
                    cursor = next_cursor
                    continue
                pin = self.handle(node.group, node.identity, role="pin")
                pending.append((node, pin))
                self.event("update_pin", node=node.identity, pin=pin.identity, depth=self.depth)
                if node.state == "INDIRECT":
                    target = self.nodes[node.slots["$target"]]
                    next_cursor = self.acquire(target)
                    self.clear_slots(node)
                    node.state = "BUSY"
                    self.drop(cursor)
                    cursor = next_cursor
                elif node.state == "THUNK":
                    captures = {name: self.acquire(self.nodes[target])
                                for name, target in node.slots.items()}
                    self.event("capture_handoff", node=node.identity,
                               owners={name: h.identity for name, h in captures.items()})
                    self.clear_slots(node)
                    node.state = "BUSY"
                    self.event("payload_cleared", node=node.identity)
                    self.drop(cursor)
                    cursor = self.callback(node, pin, captures, parent_frame=parent_frame)
                elif node.state == "APPLICATION":
                    operands = {name: self.take_slot(node, name) for name in list(node.slots)}
                    self.event("capture_handoff", node=node.identity,
                               owners={name: h.identity for name, h in operands.items()})
                    self.clear_slots(node)
                    node.state = "BUSY"
                    self.event("payload_cleared", node=node.identity)
                    self.drop(cursor)
                    function, argument = operands["$function"], operands["$argument"]
                    # Once callables are intrinsically ready and cannot be memoized.
                    # A lazy Repeat function gets its own nested Force frontier.
                    if not self.once(self.node(function).layout):
                        function = self.force(function, parent_frame=parent_frame)
                    cursor = self.invoke(function, argument, pin, parent_frame=parent_frame)
                else:
                    raise RuntimeFault("INVARIANT", f"unknown node state {node.state}")
            final = self.node(cursor)
            if expected_layout.startswith('%') and final.layout != expected_layout:
                raise RuntimeFault('INVARIANT', 'Force changed nominal sum family')
            self.validate_sum_cursor(cursor)
            # Every physical pending node gets its own slot before any pin ends.
            for destination, pin in pending:
                self.slot(destination, "$target", final)
                destination.state = "MEMO"
                destination.code = None
                self.metrics["memo_writes"] += 1
                key = "internal_memo_slots" if destination.group == final.group else "cross_group_memo_slots"
                self.metrics[key] += 1
                self.event("memo_publish", destination=destination.identity, result=final.identity,
                           pin=pin.identity, depth=self.depth, internal=destination.group == final.group)
            for destination, pin in pending:
                self.event("update_unpin", node=destination.identity, pin=pin.identity, depth=self.depth)
                self.drop(pin)
            self.event("force_return", depth=self.depth, result=final.identity, owner=cursor.identity,
                       group=final.group, layout=final.layout)
            return cursor
        finally:
            self.depth -= 1

    def boundary(self) -> None:
        self.metrics["max_loop_boundary_groups"] = max(self.metrics["max_loop_boundary_groups"], len(self.groups))
        self.metrics["max_loop_boundary_nodes"] = max(self.metrics["max_loop_boundary_nodes"], len(self.nodes))

    def block(self, body: list[dict], frame: dict[str, Handle], *, frame_id: int | None = None,
              parent_frame: int | None = None, context: dict | None = None) -> Handle | None:
        # Diagnostic identity only; never consulted by type/resource semantics.
        if frame_id is None:
            self.next_observation_frame += 1
            frame_id = self.next_observation_frame
            self.event("frame_enter", frame=frame_id, parent_frame=parent_frame,
                       context=context or {"kind": "entry"})
        for i in body:
            self.tick()
            op = i["op"]
            if op in ("retain", "drop", "borrow", "end_borrow", "application_borrow"):
                self.metrics["ir_" + op + "_ops"] += 1
            if op in ("new_root", "new_below"):
                # Check-time order witnesses are erased. Only real authority is used.
                if op == "new_below":
                    self.live(frame[i["ceiling"]])
                for imported in i["imports"]:
                    self.live(frame[imported])
                frame[i["out"]] = self.new_group()
            elif op in ('scalar', 'prim2'):
                primitive = None
                if op == 'scalar':
                    kind, value = i['kind'], i['value']
                else:
                    primitive = i['primitive']
                    left = self.ready_scalar(frame[i['left']], '#i64')
                    right = self.ready_scalar(frame[i['right']], '#i64')
                    kind = 'i64'
                    if primitive == 'addInt': value = left + right
                    elif primitive == 'subInt': value = left - right
                    elif primitive == 'mulInt': value = left * right
                    elif primitive == 'eqInt': kind, value = 'bool', left == right
                    elif primitive == 'ltInt': kind, value = 'bool', left < right
                    else: raise RuntimeFault('UNSUPPORTED', 'unknown scalar primitive')
                    if kind == 'i64': value = (value + (1 << 63)) % (1 << 64) - (1 << 63)
                handle = self.allocate(frame[i['in']], '#' + kind, 'READY', {},
                                       source_out=i['out'], frame_id=frame_id, opcode=op)
                self.node(handle).scalar = value
                frame[i['out']] = handle
                self.event('scalar_value', node=handle.node, kind=kind, value=value,
                           opcode=op, primitive=primitive)
            elif op in ('construct_nullary', 'construct_sum'):
                family, variant = i['family'], i['variant']
                variants = self.program['families'][family]['variants']
                if variant not in variants: raise RuntimeFault('INVARIANT', 'unknown sum variant')
                types = self.variant_fields(family, variant)
                values = i['fields'] if op == 'construct_sum' else []
                if len(values) != len(types): raise RuntimeFault('INVARIANT', 'sum constructor arity differs')
                fields = {}
                for index, (variable, shape) in enumerate(zip(values, types)):
                    handle = self.live(frame[variable]); node = self.node(handle)
                    if not handle.own or node.layout != shape: raise RuntimeFault('INVARIANT', 'sum field needs owned typed cursor')
                    fields[str(index)] = handle
                handle = self.allocate(frame[i['in']], '%' + family, 'READY', fields,
                                       source_out=i['out'], frame_id=frame_id, opcode=op)
                self.node(handle).variant = variant; frame[i['out']] = handle
                self.event('sum_value', node=handle.node, family='%' + family, variant=variant,
                           variant_index=variants.index(variant))
            elif op == 'case_fields_i64':
                authority = self.live(frame[i['in']])
                if not authority.own and i['in'] != '$home':
                    raise RuntimeFault('INVARIANT', 'factory needs owning or activation authority')
                family = i['family']; variants = self.program['families'][family]['variants']
                scrutinee = frame[i['scrutinee']]; variant = self.sum_tag(scrutinee, family)
                if set(i['arms']) != set(variants): raise RuntimeFault('INVARIANT', 'factory arms not exhaustive')
                # Every arm/callback/external guard precedes selected payload reads.
                for arm_variant in variants:
                    arm = i['arms'][arm_variant]; spec = self.program['codes'].get(arm['code'])
                    if not spec or spec['result'] != '#i64' or set(arm['captures']) != set(spec['captures']) or len(arm['captures']) > 64:
                        raise RuntimeFault('INVARIANT', 'factory callback signature differs')
                    fields = self.variant_fields(family, arm_variant); field_count = external_count = 0
                    for capture in sorted(spec['captures']):
                        binding = arm['captures'][capture]; layout = spec['captures'][capture]['layout']
                        if binding['kind'] == 'field':
                            index = binding['index']
                            if type(index) is not int or not 0 <= index < len(fields) or fields[index] != layout:
                                raise RuntimeFault('INVARIANT', 'factory field capture descriptor differs')
                            field_count += 1
                        elif binding['kind'] == 'external':
                            value = self.live(frame[binding['value']])
                            if not value.own or self.node(value).layout != layout:
                                raise RuntimeFault('INVARIANT', 'factory external capture not owned/exact type')
                            external_count += 1
                        else: raise RuntimeFault('INVARIANT', 'unknown factory binding kind')
                    if field_count > 32 or external_count > 32:
                        raise RuntimeFault('INVARIANT', 'factory capture bound exceeded')
                self.ready_sum(scrutinee, family); parent = self.node(scrutinee)
                if any(self.nodes[n].state == 'HOLE' for n in parent.slots.values()):
                    raise RuntimeFault('INVARIANT', 'factory selected payload still has raw construction HOLE')
                arm = i['arms'][variant]; spec = self.program['codes'][arm['code']]
                captures = {}; temporary = []; field_indices = {}; field_mask = 0
                for capture in sorted(spec['captures']):
                    binding = arm['captures'][capture]
                    if binding['kind'] == 'field':
                        index = binding['index']; target = self.nodes[parent.slots[str(index)]]
                        value = self.acquire(target); temporary.append(value); field_indices[capture] = index; field_mask |= 1 << index
                        self.event('sum_field_capture', scrutinee=parent.identity, family='%' + family,
                                   variant=variant, variant_index=variants.index(variant), capture=capture,
                                   field_index=index, node=target.identity, owner=value.identity,
                                   layout=target.layout, frame=frame_id)
                    else: value = frame[binding['value']]
                    captures[capture] = value
                result = self.allocate(authority, '#i64', 'THUNK', captures, arm['code'],
                                       source_out=i['out'], frame_id=frame_id, opcode=op)
                for value in temporary: self.drop(value)
                frame[i['out']] = result; node = self.node(result)
                self.event('case_fields_i64', scrutinee=parent.identity, family='%' + family,
                           variant=variant, variant_index=variants.index(variant), code=arm['code'],
                           result=node.identity, owner=result.identity, group=node.group, layout='#i64',
                           frame=frame_id, out=i['out'], field_mask=field_mask, captures=dict(node.slots),
                           field_indices=field_indices)
            elif op == 'case_i64':
                authority = self.live(frame[i['in']])
                if not authority.own and i['in'] != '$home':
                    raise RuntimeFault('INVARIANT', 'case needs owning or activation authority')
                family = i['family']; variants = self.program['families'][family]['variants']
                if any(self.variant_fields(family, v) for v in variants): raise RuntimeFault('INVARIANT', 'old case is nullary-only')
                scrutinee = frame[i['scrutinee']]; variant = self.ready_sum(scrutinee, family)
                if set(i['arms']) != set(variants): raise RuntimeFault('INVARIANT', 'case is not exhaustive')
                alternatives = [frame[i['arms'][v]] for v in variants]
                identities = [h.identity for h in alternatives]
                if len(set(identities)) != len(identities) or authority.identity in identities:
                    raise RuntimeFault('INVARIANT', 'case branch capabilities must be independent')
                for alternative in alternatives:
                    node = self.node(alternative)
                    if not alternative.own or alternative.loans or node.layout != '#i64' or node.state == 'HOLE':
                        raise RuntimeFault('INVARIANT', 'case needs owned typed non-ticket alternatives without loans')
                index = variants.index(variant); selected = alternatives[index]; node = self.node(selected)
                self.event('case_i64', scrutinee=scrutinee.node, family='%' + family, variant=variant,
                           variant_index=index, result=node.identity, owner=selected.identity,
                           group=node.group, layout=node.layout, frame=frame_id, out=i['out'],
                           alternatives={v: h.node for v, h in zip(variants, alternatives)})
                for variable in i['arms'].values(): del frame[variable]
                for j, alternative in enumerate(alternatives):
                    if j != index: self.drop(alternative)
                frame[i['out']] = selected
            elif op == 'select_i64':
                authority = self.live(frame[i['in']])
                if not authority.own and i['in'] != '$home':
                    raise RuntimeFault('INVARIANT', 'selection needs owning or activation authority')
                condition = frame[i['condition']]
                decision = self.ready_scalar(condition, '#bool')
                left, right = frame[i['then']], frame[i['else']]
                if left.identity == right.identity or authority.identity in (left.identity, right.identity):
                    raise RuntimeFault('INVARIANT', 'selection branch capabilities must be independent')
                for alternative in (left, right):
                    node = self.node(alternative)
                    if not alternative.own or alternative.loans or node.layout != '#i64' or node.state == 'HOLE':
                        raise RuntimeFault('INVARIANT', 'selection requires owned typed non-ticket cursors without loans')
                selected, unselected = (left, right) if decision else (right, left)
                node = self.node(selected)
                self.event('select_i64', condition_node=condition.node, condition_value=decision,
                           then_node=left.node, else_node=right.node, result=node.identity,
                           owner=selected.identity, group=node.group, layout=node.layout,
                           frame=frame_id, out=i['out'])
                del frame[i['then']]; del frame[i['else']]
                self.drop(unselected)
                frame[i['out']] = selected
            elif op in ("alloc", "thunk", "hole", "closure", "application", "application_borrow"):
                moved = []
                if op in ("application", "application_borrow"):
                    signature = self.signature(self.node(frame[i["function"]]).layout)
                    layout, state, code = signature["result"], "APPLICATION", None
                    fields = {"$function": frame[i["function"]], "$argument": frame[i["argument"]]}
                    moved = [variable for variable in (i["function"], i["argument"])
                             if self.once(self.node(frame[variable]).layout)]
                    self.metrics["applications_allocated"] += 1
                elif op in ("thunk", "closure"):
                    if op == "closure":
                        spec = self.program["functions"][i["function"]]
                        layout, state, code = "@" + spec["signature"], "CLOSURE", i["function"]
                        moved = [variable for variable in i["captures"].values()
                                 if self.once(self.node(frame[variable]).layout)]
                    else:
                        spec = self.program["codes"][i["code"]]
                        layout, state, code = spec["result"], "THUNK", i["code"]
                    fields = {name: frame[var] for name, var in i["captures"].items()}
                else:
                    layout, state, code = i["layout"], "READY" if op == "alloc" else "HOLE", None
                    fields = {name: frame[var] for name, var in i.get("fields", {}).items()}
                frame[i["out"]] = self.allocate(frame[i["in"]], layout, state, fields, code,
                                                move_tokens=op in ("closure", "application"),
                                                source_out=i["out"], frame_id=frame_id, opcode=op)
                if op == "application_borrow":
                    self.metrics["borrowed_slot_publications"] += sum(not h.own for h in fields.values())
                    self.event("borrowed_slots_published", node=frame[i["out"]].node,
                               anchors={field: h.anchor for field, h in fields.items() if not h.own})
                for variable in moved:
                    self.drop(frame.pop(variable))
            elif op == "call":
                authority = frame[i["in"]]
                callee, argument = frame.pop(i["function"]), frame.pop(i["argument"])
                frame[i["out"]] = self.invoke(callee, argument, authority, parent_frame=frame_id)
            elif op == "fill":
                node, target = self.node(frame[i["hole"]]), self.node(frame[i["value"]])
                if node.state != "HOLE":
                    raise RuntimeFault("INVARIANT", "construction ticket reused")
                self.slot(node, "$target", target)
                node.state = "INDIRECT"
                self.event("fill", hole=node.identity, target=target.identity, frame=frame_id,
                           hole_variable=i["hole"], value_variable=i["value"])
            elif op == "borrow":
                source = self.live(frame[i["value"]])
                frame[i["out"]] = self.handle(source.group, source.node, anchor=source)
            elif op == "field":
                source = self.live(frame[i["value"]])
                target = self.nodes[self.node(source).slots[i["field"]]]
                frame[i["out"]] = self.handle(target.group, target.identity, anchor=source)
                self.event("field_project", host=source.node, host_group=source.group,
                           field=i["field"], target=target.identity, target_group=target.group,
                           target_layout=target.layout, anchor=source.identity,
                           loan=frame[i["out"]].identity, out=i["out"],
                           source_variable=i["value"], frame=frame_id)
            elif op == "retain":
                source = self.live(frame[i["value"]])
                frame[i["out"]] = self.acquire(self.node(source))
            elif op in ("drop", "end_borrow"):
                self.drop(frame.pop(i["value"]))
            elif op == "force":
                frame[i["out"]] = self.force(frame.pop(i["value"]), parent_frame=frame_id)
            elif op == "loop":
                cursor = frame.pop(i["cursor"])
                self.boundary()
                for _ in range(i["count"]):
                    self.tick()
                    pin = self.handle(cursor.group, role="pin")
                    home = self.handle(cursor.group, anchor=pin)
                    inner = {"$home": home, i["as"]: cursor}
                    result = self.block(i["body"], inner, parent_frame=frame_id,
                                        context={"kind": "loop", "out": i["out"]})
                    if result is None:
                        raise RuntimeFault("INVARIANT", "loop did not return owned cursor")
                    self.live(result)
                    self.drop(home)
                    self.drop(pin)
                    cursor = result
                    self.metrics["loop_iterations"] += 1
                    self.boundary()
                frame[i["out"]] = cursor
            elif op == "choose":
                return self.block(i["then"] if i["condition"] else i["else"], frame, frame_id=frame_id)
            elif op == "return":
                self.validate_sum_cursor(frame[i["value"]])
                result = frame.pop(i["value"])
                if not result.own or set(frame) != {"$home"}:
                    raise RuntimeFault("INVARIANT", "incorrect return custody")
                if self.once(self.node(result).layout) and result.token is None:
                    raise RuntimeFault("INVARIANT", "Once result lacks its transferred permission")
                return result
            elif op == 'finish_scalar':
                handle = frame[i['value']]
                layout = self.node(handle).layout
                value = self.ready_scalar(handle, layout)
                if set(frame) != {i['value']} or handle.loans:
                    raise RuntimeFault('INVARIANT', 'scalar finish leaked local capabilities')
                self.drop(frame.pop(i['value']))
                if self.handles or self.groups or self.nodes or self.closing or self.tokens:
                    raise RuntimeFault('INVARIANT', 'scalar finish left managed storage')
                self.result = {'kind': layout[1:], 'value': value}
                return None
            elif op == "finish":
                if frame:
                    raise RuntimeFault("INVARIANT", "entry leaked local handles")
                return None
            else:
                raise RuntimeFault("INVARIANT", "unchecked operation reached runtime")
        raise RuntimeFault("INVARIANT", "unterminated block")

    def run(self) -> dict:
        self.block(self.program["entry"], {})
        if self.handles or self.groups or self.nodes or self.closing or self.tokens:
            raise RuntimeFault("INVARIANT", "finished program left managed storage or capabilities")
        return {"status": "completed", "sha256": self.checked.sha256, "result": self.result, "metrics": {
                    **self.metrics, "live_groups": len(self.groups), "live_nodes": len(self.nodes),
                    "live_handles": len(self.handles)},
                "live_tokens": len(self.tokens),
                "observation_schema": "resource-ir-slots-and-projections/1",
                "events": self.events, "events_omitted": self.events_omitted,
                "space_metric": "managed IR groups/cells only, not Python heap or RSS"}


def run(program: dict | CheckedProgram, *, fuel: int = 1_000_000, event_limit: int = 0) -> dict:
    """Recheck precisely the immutable snapshot that will be executed.

    A manually constructed CheckedProgram or caller-supplied hash is not trusted.
    The original mutable dictionary is never used after checking.
    """
    if type(fuel) is not int or fuel <= 0 or type(event_limit) is not int or event_limit < 0:
        raise ValueError("fuel must be positive and event_limit nonnegative integers")
    checked = check(program.data() if isinstance(program, CheckedProgram) else program)
    try:
        return _Machine(checked, fuel, event_limit).run()
    except RecursionError as exc:
        raise RuntimeFault("HOST_STACK_LIMIT", "host interpreter recursion limit; no cleanup claim") from exc
