"""Independent wire and row models for the generated data-processing workloads."""
import re
import unittest

import data_shapes


def packet(n, seed):
    tokens = []
    value = seed
    total = 0
    for pos in range(1, n + 1):
        value = (value + 7) % 29
        total += pos + value
        tokens.extend(((pos - 1) % 3 + 1, value, total % 251))
    return tokens


def parse_packet(tags, tokens):
    check = 0
    for offset, expected_tag in enumerate(tags):
        start = 3 * offset
        field = tokens[start:start + 3]
        if len(field) != 3 or field[0] != expected_tag:
            return -(offset + 1)
        check = (check + offset + 1 + field[1]) % 251
        if check != field[2]:
            return -(offset + 1)
    return check + 1 if len(tokens) == 3 * len(tags) else -(len(tags) + 1)


class DataShapeTests(unittest.TestCase):
    def test_table_contains_distinct_irregular_rows_and_scores_their_positions(self):
        family = 'irregular_literal_table'
        for n in (1, 2, 3, 8, 32, 128, 8192):
            declarations, entry = data_shapes.program_body(family, n)
            self.assertEqual(entry, 'checksum (addInt x 1) table')
            table = declarations.split('table = ')[1]
            rows = [(int(key), int(value)) for key, value in re.findall(r'More \(Row (\d+) (\d+)\) \(', table)]
            self.assertEqual(len(rows), n)
            self.assertEqual(table.count('Empty'), 1)
            self.assertTrue(table.endswith('Empty' + ')' * n + ';\n'))
            for i, (key, value) in enumerate(rows):
                self.assertEqual(key, i + 1)
                self.assertEqual(value, (17 * i**2 + 7 * i + 11) % 257)
            self.assertTrue(all(c[1] - b[1] != b[1] - a[1] for a, b, c in zip(rows, rows[1:], rows[2:])))
            self.assertIn('mulInt weight (addInt (mulInt 257 key) value)', declarations)
            self.assertIn('checksum (addInt weight 1) rest', declarations)
            for x in (-n - 1, *data_shapes.inputs(family, n)):
                def score(stored):
                    return sum(weight * (257 * key + value)
                               for weight, (key, value) in enumerate(stored, start=x + 1))
                want = data_shapes.expected(family, n, x)
                self.assertEqual(score(rows), want)
                self.assertLess(abs(want), 2**63)
                if n > 1:
                    self.assertNotEqual(score([rows[-1], *rows[1:-1], rows[0]]), want)

    def test_decoder_steps_consume_fields_in_order_and_check_the_remaining_stream(self):
        for n in (1, 8, 32, 128, 8192):
            declarations, entry = data_shapes.program_body('decoder_pipeline', n)
            steps = re.findall(r'^decode(\d+) previous bytes = readField (\d+) (\d+) (\w+) previous bytes;$',
                               declarations, re.MULTILINE)
            self.assertEqual(steps, [(str(i), str(i), str((i - 1) % 3 + 1),
                                      f'decode{i + 1}' if i < n else 'finish') for i in range(1, n + 1)])
            self.assertEqual(entry, 'decode1 0 (encode x (andInt x 15) 1 0)')
            self.assertIn('Byte tag (Byte value (Byte wireCheck rest))', declarations)
            self.assertIn('eqInt tag want then if eqInt check wireCheck then next check rest', declarations)
            self.assertIn('case bytes of { End -> addInt check 1;', declarations)

    def test_decoder_oracle_and_signed_inputs_exercise_first_middle_last_and_short_fields(self):
        family = 'decoder_pipeline'
        for n in (1, 2, 3, 8, 31, 128, 8192):
            probes = data_shapes.inputs(family, n)
            self.assertEqual(len(probes), len(set(probes)))
            self.assertTrue({0, 1, (n + 1) // 2, n, -((n + 1) // 2), n + 1} <= set(probes))
            tags = [(1, 2, 3)[i % 3] for i in range(n)]
            for x in (range(-n - 1, n + 2) if n <= 31 else probes):
                tokens = packet(n, x & 15)
                if 1 <= x <= n:
                    tokens[3 * x - 1] += 1
                elif -n <= x < 0:
                    del tokens[3 * (-x - 1) + 1:]
                self.assertEqual(data_shapes.expected(family, n, x), parse_packet(tags, tokens))

    def test_decoder_rejects_field_mutations_at_the_earliest_error(self):
        n = 8
        tags = [(1, 2, 3)[i % 3] for i in range(n)]
        good = packet(n, 0)
        for pos in range(1, n + 1):
            start = 3 * (pos - 1)
            for field in range(3):
                damaged = good.copy()
                damaged[start + field] += 1
                if pos < n:
                    damaged[-1] += 1
                self.assertEqual(parse_packet(tags, damaged), data_shapes.expected('decoder_pipeline', n, pos))
                self.assertEqual(parse_packet(tags, good[:start + field]),
                                 data_shapes.expected('decoder_pipeline', n, -pos))
        self.assertEqual(parse_packet(tags, [*good, 1]), -(n + 1))


if __name__ == '__main__':
    unittest.main()
