#!/usr/bin/env python3

from .__about__ import (__summary__, __title__)
from ruamel.yaml import YAML
from ruamel.yaml.error import MarkedYAMLError

import collections
from enum import Enum
from itertools import zip_longest
import os
import sys

try:
    import colorama
    from colorama import Fore, Style
    colorama.init()
except ImportError:
    class Dummy:
        def __getattribute__(self, name):
            return ''
    Fore = Dummy()
    Style = Dummy()


class DiffError(Exception):
    pass


class DiffContext:
    def __init__(self, line, col):
        """Creates a DiffContext

        Args:
         - line (int): Line number (1-based, so human-readable)
         - col (int): Column number (1-based, so human-readable)
        """
        self.line = line
        self.col = col

    @staticmethod
    def from_lc(lc):
        """Convenience method for creating a DiffContext from a ruamel.yaml context object"""
        if hasattr(lc, 'line'):
            # ruamel.yaml context object with 'line' and 'col' properties
            return DiffContext(lc.line+1, lc.col+1)
        else:
            # Tuple (line, col), as returned by `lc.key(x)` etc.
            return DiffContext(lc[0]+1, lc[1]+1)


class Diff:
    def __init__(self, left, right, left_context=None, right_context=None):
        """Stores information on the difference between a Left and Right YAML document"""
        self.left = left
        self.right = right
        if left_context:
            if isinstance(left_context, DiffContext):
                self.left_context = left_context
            else:
                self.left_context = DiffContext(*left_context)
        else:
            self.left_context = None
        if right_context:
            if isinstance(right_context, DiffContext):
                self.right_context = right_context
            else:
                self.right_context = DiffContext(*right_context)
        else:
            self.right_context = None


class NodeType(Enum):
    NULL = 'null'
    MAP = 'map'
    LIST = 'sequence'
    SCALAR = 'scalar'


class YamlDiffer:
    """Computes semantic differences between YAML files"""

    def diff_yaml_files(self, left, right, skip_header_doc=False):
        """Diffs two YAML files

        Args:
            left (str): path to the left YAML file
            right (str): path to the right YAML file
            skip_header_doc (bool): if True, skips the first document
                (assumed to contain header information) in the YAML file

        Returns:
            array of Diff objects, or empty array if files are identical
        """
        with open(left, 'rb') as f_left, open(right, 'rb') as f_right:
            return self.diff_yaml_streams(f_left, f_right, skip_header_doc=skip_header_doc)

    def diff_yaml_streams(self, left, right, skip_header_doc=False):
        """Diffs two YAML streams or strings

        Args:
            left (stream or str): left YAML file
            right (stream or str): right YAML file
            skip_header_doc (bool): if True, skips the first document
                (assumed to contain header information) in the YAML file

        Returns:
            array of Diff objects, or empty array if files are identical
        """
        y = YAML(typ='rt')

        def try_load(stream, side_name):
            try:
                contents = list(y.load_all(stream))
                if skip_header_doc:
                    if len(contents) < 2:
                        raise DiffError('Cannot skip header: no header YAML document found')
                    contents = contents[1:]
                return contents
            except MarkedYAMLError as e:
                stream_name = stream.name if hasattr(stream, 'name') else side_name
                raise DiffError(
                    f'Error parsing YAML stream "{stream_name}":\n' +
                    f'{e.problem_mark.line+1}:{e.problem_mark.column+1} {e.context}: {e.problem}')

        contents_l = try_load(left, 'left')
        contents_r = try_load(right, 'right')

        diffs = []
        max_len = max([len(contents_l), len(contents_r)])
        for idx, doc_l, doc_r in zip_longest(range(max_len), contents_l, contents_r):
            if doc_l is None:
                diffs.append(Diff('<no document>', f'<YAML document #{idx+1}>',
                            right_context=DiffContext.from_lc(doc_r.lc)))
            elif doc_r is None:
                diffs.append(Diff(f'<YAML document #{idx+1}>', '<no document>',
                            left_context=DiffContext.from_lc(doc_l.lc)))
            else:
                diffs += self.diff_yaml_docs(doc_l, doc_r)
        return diffs

    def diff_yaml_docs(self, left, right):
        """Diffs two parsed YAML documents

        Args:
            left (array of YAML docs): left YAML file
            right (array of YAML docs): right YAML file

        Returns:
            array of Diff objects, or empty array if files are identical
        """
        type_l = self._node_type(left)
        type_r = self._node_type(right)
        if type_l == type_r:
            if type_l == NodeType.MAP:
                return self._diff_yaml_maps(left, right)
            elif type_l == NodeType.LIST:
                return self._diff_yaml_lists(left, right)
            else:
                raise DiffError('Unknown YAML root node type')
        else:
            return Diff(f'<top-level node of type {type_l.value}>',
                        f'<top-level node of type {type_r.value}>',
                        DiffContext.from_lc(left.lc) if type_l != NodeType.NULL else None,
                        DiffContext.from_lc(right.lc) if type_r != NodeType.NULL else None)

    @staticmethod
    def _node_type(x):
        if x is None:
            return NodeType.NULL
        elif isinstance(x, collections.Mapping):
            return NodeType.MAP
        elif isinstance(x, collections.abc.Sequence) and not isinstance(x, str):
            return NodeType.LIST
        else:
            return NodeType.SCALAR

    def _diff_yaml_maps(self, left, right):
        assert self._node_type(left) == NodeType.MAP and self._node_type(right) == NodeType.MAP
        diffs = []
        for key, value in left.items():
            if key not in right:
                diffs.append(Diff(str(key), '<missing key>',
                                DiffContext.from_lc(left.lc.key(key)),
                                DiffContext.from_lc(right.lc)))
                continue
            type_l = self._node_type(left[key])
            type_r = self._node_type(right[key])
            if type_l == type_r:
                if type_l == NodeType.NULL:
                    pass
                elif type_l == NodeType.LIST:
                    diffs += self._diff_yaml_lists(value, right[key])
                elif type_l == NodeType.MAP:
                    diffs += self._diff_yaml_maps(value, right[key])
                elif type_l == NodeType.SCALAR:
                    if value != right[key]:
                        diffs.append(Diff(str(value), str(right[key]),
                                        DiffContext.from_lc(left.lc.value(key)),
                                        DiffContext.from_lc(right.lc.value(key))))
            else:
                diffs.append(Diff(f'<node of type {type_l.value}> {key}', f'<node of type {type_r.value}> {key}',
                                DiffContext.from_lc(left.lc.value(key)),
                                DiffContext.from_lc(right.lc.value(key))))
        for key, value in right.items():
            if key not in left:
                diffs.append(Diff('<missing key>', str(key),
                                DiffContext.from_lc(left.lc),
                                DiffContext.from_lc(right.lc.key(key))))
        return diffs

    def _diff_yaml_lists(self, left, right):
        assert self._node_type(left) == NodeType.LIST and self._node_type(right) == NodeType.LIST
        diffs = []
        max_len = max([len(left), len(right)])
        for idx, item_l, item_r in zip_longest(range(max_len), left, right):
            if item_l is None:
                diffs.append(Diff('<missing item>', str(item_r),
                                DiffContext.from_lc(left.lc),
                                DiffContext.from_lc(right.lc.item(idx))))
            elif item_r is None:
                diffs.append(Diff(str(item_l), '<missing item>',
                                DiffContext.from_lc(left.lc.item(idx)),
                                DiffContext.from_lc(right.lc)))
            else:
                type_l = self._node_type(item_l)
                type_r = self._node_type(item_r)
                if type_l == type_r:
                    if type_l == NodeType.NULL:
                        pass
                    elif type_l == NodeType.LIST:
                        diffs += self._diff_yaml_lists(item_l, item_r)
                    elif type_l == NodeType.MAP:
                        diffs += self._diff_yaml_maps(item_l, item_r)
                    elif type_l == NodeType.SCALAR:
                        if item_l != item_r:
                            diffs.append(Diff(str(item_l), str(item_r),
                                            DiffContext.from_lc(left.lc.item(idx)),
                                            DiffContext.from_lc(right.lc.item(idx))))
                else:
                    diffs.append(Diff(f'<node of type {type_l.value}>', f'<node of type {type_r.value}>',
                                    DiffContext.from_lc(left.lc.item(idx)),
                                    DiffContext.from_lc(right.lc.item(idx))))
        return diffs


def pretty_print_diffs(diffs, col_width=40, separator='<->', context=0,
                       left=None, right=None):
    if (context > 0) and ((left is None) or (right is None)):
        # Cannot show context if file data is missing
        context = 0
    if context > 0:
        lines_l = left.splitlines()
        lines_r = right.splitlines()

    def shorten_and_pad(s, width, placeholder=''):
        assert width > len(placeholder)
        if len(s) > width:
            s = s[:width-len(placeholder)] + placeholder
        else:
            s += ' '*(width - len(s))
        return s
    def side_to_str(prefix, side, side_context):
        context = f'{side_context.line: 4d}:{side_context.col:<3d}' if side_context else ' '*8
        side_str = shorten_and_pad(side, col_width-10, placeholder='...')
        return f'{prefix}{context} {side_str}'
    def diff_to_str(self):
        ls = side_to_str('L', self.left, self.left_context)
        rs = side_to_str('R', self.right, self.right_context)
        return ls + separator + rs
    def get_context_line(lines, diff_context, offset):
        if diff_context:
            try:
                return shorten_and_pad(lines[diff_context.line - 1 + offset], col_width)
            except IndexError:
                pass
        return ' '*col_width

    for d in diffs:
        print(Fore.BLUE if context else Fore.RESET, end='')
        print(diff_to_str(d))
        if context:
            for offset in range(-context, context+1):
                print(Fore.RED if offset == 0 else Fore.RESET, end='')
                print(get_context_line(lines_l, d.left_context, offset) +
                      ' '*len(separator) +
                      get_context_line(lines_r, d.right_context, offset))
            print()


def main():
    import argparse

    parser = argparse.ArgumentParser(description='YAML Diff Tool')
    parser.add_argument('left', type=argparse.FileType(mode='r'),
                        help='Left YAML file')
    parser.add_argument('right', type=argparse.FileType(mode='r'),
                        help='Right YAML file')
    parser.add_argument('--context', '-C', type=int, default=0,
                        help='Number of lines of context to print with each difference (default: 0)')
    parser.add_argument('-x', '--skip-header-doc', action='store_true',
                        help='Skip the first document with header information in the YAML stream')
    args = parser.parse_args()

    # Diff given files
    differ = YamlDiffer()
    try:
        diffs = differ.diff_yaml_streams(
            args.left, args.right,
            skip_header_doc=args.skip_header_doc)
    except DiffError as e:
        print(str(e))
        sys.exit(2)

    # Output differences
    def fit_path(s, width):
        if len(s) <= width:
            return s + ' '*(width-len(s))
        else:
            return '...' + s[-width+3:]
    SEPARATOR = '<->'
    try:
        col_width = max([20, os.get_terminal_size()[0]//2 - len(SEPARATOR)//2 - 1])
    except OSError:
        col_width = 40

    if diffs:
        print(Style.BRIGHT +
              'L:' + fit_path(args.left.name, col_width-2) +
              ' '*len(SEPARATOR) +
              'R:' + fit_path(args.right.name, col_width-2) +
              Style.RESET_ALL)
        args.left.seek(0)
        args.right.seek(0)
        pretty_print_diffs(
            diffs, col_width=col_width, separator=SEPARATOR, context=args.context,
            left=args.left.read(), right=args.right.read())
        print(Style.BRIGHT + f'{len(diffs)} difference(s) found.' + Style.RESET_ALL)
    else:
        print('The given files are identical.')


if __name__ == '__main__':
    main()
