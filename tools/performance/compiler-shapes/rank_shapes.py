"""Program shapes for nested type depth and separately checked higher-rank consumers."""


def program_body(family, n, balanced):
    if family == 'nested_poly_types':
        declarations = (
            'data Box a = Box a;\n'
            'hold :: forall a. a -> Box a;\nhold y = Box y;\n'
            'unbox :: forall a. Box a -> a;\nunbox b = case b of { Box y -> y };\n'
        )
        expression = 'unbox (' * n + 'hold (' * n + 'x' + ')' * (2 * n)
        return declarations, expression

    if family == 'rank2_callbacks':
        declarations = ['identity :: forall a. a -> a;\nidentity value = value;\n']
        terms = []
        for i in range(n):
            declarations.append(
                f'consume{i} :: (forall a. a -> a) -> Int -> Int;\n'
                f'consume{i} callback x = let {{ value = callback (addInt x {i}) }} in '
                f'if callback (ltInt x {i}) then addInt value {i + 1} '
                f'else subInt value {i + 1};\n'
            )
            terms.append(f'consume{i} identity x')
        return ''.join(declarations), balanced(terms, lambda a, b: f'addInt ({a}) ({b})')

    raise ValueError(family)


def expected(family, n, x):
    if family == 'nested_poly_types':
        return x
    if family == 'rank2_callbacks':
        # Consumers whose index is <= x return x - 1. Each later index i
        # contributes an additional 2*(i+1) to that baseline.
        count = max(0, min(n, x + 1))
        total = n * (x - 1) + n * (n + 1) - count * (count + 1)
        return (total + 2**63) % 2**64 - 2**63
    raise ValueError(family)
