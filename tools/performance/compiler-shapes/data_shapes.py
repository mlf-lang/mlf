"""Compiler shapes for irregular constructor constants and a sequential decoder."""


def irregular_table(n):
    # Finite differences encode the polynomial specified independently in expected().
    # A nonzero second difference mod 257 prevents any three payloads forming a stride.
    payload, difference = 11, 24
    rows = []
    for key in range(1, n + 1):
        rows.append(f'More (Row {key} {payload}) (')
        payload = (payload + difference) % 257
        difference = (difference + 34) % 257
    table = ''.join(rows) + 'Empty' + ')' * n
    declarations = (
        'data Row = Row Int Int;\n'
        'data Rows = Empty | More Row Rows;\n'
        'checksum :: Int -> Rows -> Int;\n'
        'checksum weight rows = case rows of { Empty -> 0; More row rest -> case row of { '
        'Row key value -> addInt (mulInt weight (addInt (mulInt 257 key) value)) '
        '(checksum (addInt weight 1) rest) } };\n'
        f'table :: Rows;\ntable = {table};\n'
    )
    return declarations, 'checksum (addInt x 1) table'


def decoder(n):
    # The runtime encoder provides tag, payload and checksum tokens. Only advancing
    # past a validated field invokes the continuation for the next schema field.
    declarations = [
        'data Bytes = End | Byte Int Bytes;\n',
        'encode :: Int -> Int -> Int -> Int -> Bytes;\n',
        f'encode fault seed pos previous = if ltInt {n} pos then End else let {{\n',
        'tag = addInt 1 (remInt (subInt pos 1) 3);\n',
        'value = remInt (addInt (mulInt 7 pos) seed) 29;\n',
        'check = remInt (addInt previous (addInt value pos)) 251;\n',
        'wireCheck = if eqInt fault pos then addInt check 1 else check\n',
        '} in if eqInt fault (subInt 0 pos) then Byte tag End else '
        'Byte tag (Byte value (Byte wireCheck (encode fault seed (addInt pos 1) check)));\n',
        'readField :: Int -> Int -> (Int -> Bytes -> Int) -> Int -> Bytes -> Int;\n',
        'readField pos want next previous bytes = case bytes of { '
        'Byte tag (Byte value (Byte wireCheck rest)) -> '
        'let { check = remInt (addInt (addInt previous pos) value) 251 } in '
        'if eqInt tag want then if eqInt check wireCheck then next check rest '
        'else subInt 0 pos else subInt 0 pos; _ -> subInt 0 pos };\n',
        'finish :: Int -> Bytes -> Int;\n',
        f'finish check bytes = case bytes of {{ End -> addInt check 1; Byte value rest -> subInt 0 {n + 1} }};\n',
    ]
    for pos in range(1, n + 1):
        successor = 'finish' if pos == n else f'decode{pos + 1}'
        tag = (pos - 1) % 3 + 1
        declarations.append(f'decode{pos} :: Int -> Bytes -> Int;\n'
                            f'decode{pos} previous bytes = readField {pos} {tag} {successor} previous bytes;\n')
    return ''.join(declarations), 'decode1 0 (encode x (andInt x 15) 1 0)'


def program_body(family, n):
    if family == 'irregular_literal_table':
        return irregular_table(n)
    if family == 'decoder_pipeline':
        return decoder(n)
    raise ValueError(family)


def expected(family, n, x):
    if family == 'irregular_literal_table':
        return sum((x + i + 1) * (257 * (i + 1) + (17 * i * i + 7 * i + 11) % 257)
                   for i in range(n))
    if family == 'decoder_pipeline':
        if 1 <= abs(x) <= n:
            return -abs(x)
        seed = x & 15
        payload_sum = sum((7 * pos + seed) % 29 for pos in range(1, n + 1))
        return 1 + (payload_sum + n * (n + 1) // 2) % 251
    raise ValueError(family)


def inputs(family, n):
    if family == 'irregular_literal_table':
        return [-1, 0, 7]
    if family == 'decoder_pipeline':
        middle = (n + 1) // 2
        return list(dict.fromkeys([0, 1, middle, n, -middle, n + 1]))
    raise ValueError(family)
