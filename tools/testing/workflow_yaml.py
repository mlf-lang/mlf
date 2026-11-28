"""Read workflow semantics with a real YAML parser, without YAML 1.1's `on` bool.

This is a test dependency, not part of the compiler or package manager. Install
``python3 -m pip install -r tools/testing/requirements.txt`` before these tests.
Actionlint remains responsible for the complete GitHub Actions schema.
"""
import json
import re
import sys

try:
    import yaml
except ImportError as error:
    raise SystemExit(
        'Workflow tests require PyYAML; install with '
        'python3 -m pip install -r tools/testing/requirements.txt'
    ) from error


class WorkflowLoader(yaml.SafeLoader):
    pass


WorkflowLoader.yaml_implicit_resolvers = {
    key: [(tag, pattern) for tag, pattern in values
          if tag != 'tag:yaml.org,2002:bool']
    for key, values in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
WorkflowLoader.add_implicit_resolver(
    'tag:yaml.org,2002:bool', re.compile(r'^(?:true|false)$', re.I), list('tTfF'))


def unique_mapping(loader, node, deep=False):
    # Explicit duplicates are ambiguous. YAML merge keys may legitimately be
    # overridden by a later explicit field, which SafeLoader already handles.
    seen = set()
    for key_node, _ in node.value:
        if key_node.tag == 'tag:yaml.org,2002:merge':
            continue
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            raise ValueError('duplicate workflow key: ' + str(key))
        seen.add(key)
    loader.flatten_mapping(node)
    return yaml.SafeLoader.construct_mapping(loader, node, deep=deep)


WorkflowLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def load(text):
    value = yaml.load(text, Loader=WorkflowLoader)
    if not isinstance(value, dict):
        raise ValueError('workflow must be a mapping')
    return value


if __name__ == '__main__':
    json.dump(load(sys.stdin.read()), sys.stdout)
