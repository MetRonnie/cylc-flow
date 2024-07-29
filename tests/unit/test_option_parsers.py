# THIS FILE IS PART OF THE CYLC WORKFLOW ENGINE.
# Copyright (C) NIWA & British Crown (Met Office) & Contributors.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import io
import shlex
import sys
from contextlib import redirect_stdout
from types import SimpleNamespace
from typing import Iterable, List

import pytest
from pytest import param

import cylc.flow.flags
from cylc.flow.option_parsers import (
    CylcOption,
    CylcOptionParser as COP,
    Options,
    cleanup_sysargv,
    combine_options,
    combine_options_pair,
    filter_sysargv,
)
from cylc.flow.scripts.install import INSTALL_OPTIONS


USAGE_WITH_COMMENT = "usage \n # comment"
OPTS = 'opts'
ATTRS = 'attrs'
SOURCES = 'sources'
USEIF = 'useif'


def get_option_by_name(
    opts: Iterable[CylcOption], name: str
) -> CylcOption:
    """Get an CylcOption object by name from a list of CylcOptions."""
    try:
        return next((x for x in opts if x.dest == name))
    except StopIteration:
        raise ValueError(name)


@pytest.fixture(scope='module')
def parser():
    return COP(
        USAGE_WITH_COMMENT,
        argdoc=[('SOME_ARG', "Description of SOME_ARG")]
    )


@pytest.mark.parametrize(
    'args,verbosity',
    [
        ([], 0),
        (['-v'], 1),
        (['-v', '-v', '-v'], 3),
        (['-q'], -1),
        (['-q', '-q', '-q'], -3),
        (['-q', '-v', '-q'], -1),
        (['--debug'], 2),
        (['--debug', '-q'], 1),
        (['--debug', '-v'], 3),
    ]
)
def test_verbosity(
    args: List[str],
    verbosity: int,
    parser: COP, monkeypatch: pytest.MonkeyPatch
) -> None:
    """-v, -q, --debug should be additive."""
    # patch the cylc.flow.flags value so that it gets reset after the test
    monkeypatch.setattr('cylc.flow.flags.verbosity', None)
    opts, args = parser.parse_args(['default-arg'] + args)
    assert opts.verbosity == verbosity
    # test side-effect, the verbosity flag should be set
    assert cylc.flow.flags.verbosity == verbosity


def test_help_color(monkeypatch: pytest.MonkeyPatch, parser: COP):
    """Test for colorized comments in 'cylc cmd --help --color=always'."""
    # This colorization is done on the fly when help is printed.
    monkeypatch.setattr("sys.argv", ['cmd', 'foo', '--color=always'])
    parser.parse_args(None)
    assert parser.values.color == "always"
    f = io.StringIO()
    with redirect_stdout(f):
        parser.print_help()
    assert not (f.getvalue()).startswith("Usage: " + USAGE_WITH_COMMENT)


def test_help_nocolor(monkeypatch: pytest.MonkeyPatch, parser: COP):
    """Test for no colorization in 'cylc cmd --help --color=never'."""
    # This colorization is done on the fly when help is printed.
    monkeypatch.setattr(sys, "argv", ['cmd', 'foo', '--color=never'])
    parser.parse_args(None)
    assert parser.values.color == "never"
    f = io.StringIO()
    with redirect_stdout(f):
        parser.print_help()
    assert (f.getvalue()).startswith("Usage: " + USAGE_WITH_COMMENT)


def test_Options_std_opts():
    """Test Python Options API with standard options."""
    parser = COP(USAGE_WITH_COMMENT, auto_add=True)
    MyOptions = Options(parser)
    MyValues = MyOptions(verbosity=1)
    assert MyValues.verbosity == 1


# Add overlapping args tomorrow
@pytest.mark.parametrize(
    'first, second, expect',
    [
        param(
            [CylcOption('-f', '--foo', sources={'do'})],
            [CylcOption('-f', '--foo', sources={'dont'})],
            [CylcOption('-f', '--foo', sources={'do', 'dont'})],
            id='identical arg lists unchanged',
        ),
        param(
            [CylcOption('-f', '--foo', sources={'fall'})],
            [
                CylcOption(
                    '-f', '--foolish', sources={'fold'}, help='not identical'
                )
            ],
            [
                CylcOption('--foo', sources={'fall'}),
                CylcOption(
                    '--foolish', sources={'fold'}, help='not identical'
                ),
            ],
            id='different arg lists lose shared names',
        ),
        param(
            [CylcOption('-f', '--foo', sources={'cook'})],
            [
                CylcOption(
                    '-f', '--foo',
                    sources={'bake'}, help='not identical', dest='foobius',
                )
            ],
            None,
            id='different args identical arg list cause exception',
        ),
        param(
            [CylcOption('-g', '--goo', sources={'knit'})],
            [CylcOption('-f', '--foo', sources={'feed'})],
            [
                CylcOption('-g', '--goo', sources={'knit'}),
                CylcOption('-f', '--foo', sources={'feed'}),
            ],
            id='all unrelated args added',
        ),
        param(
            [
                CylcOption('-f', '--foo', sources={'work'}),
                CylcOption('-r', '--redesdale', sources={'work'}),
            ],
            [
                CylcOption('-f', '--foo', sources={'sink'}),
                CylcOption('-b', '--buttered-peas', sources={'sink'}),
            ],
            [
                CylcOption('-f', '--foo', sources={'work', 'sink'}),
                CylcOption('-b', '--buttered-peas', sources={'sink'}),
                CylcOption('-r', '--redesdale', sources={'work'}),
            ],
            id='do not repeat args',
        ),
        param(
            [CylcOption('-f', '--foo', sources={'push'})],
            [],
            [CylcOption('-f', '--foo', sources={'push'})],
            id='one empty list is fine',
        ),
    ],
)
def test_combine_options_pair(first, second, expect):
    """It combines sets of options"""
    if expect is not None:
        result = combine_options_pair(first, second)
        assert [
            (o.opts, o.sources, o.useif, o.attrs) for o in result
        ] == [
            (o.opts, o.sources, o.useif, o.attrs) for o in expect
        ]
    else:
        with pytest.raises(Exception, match='Clashing Options'):
            combine_options_pair(first, second)


@pytest.mark.parametrize(
    'inputs, expect',
    [
        param(
            [
                ([CylcOption(
                    '-i', '--inflammable', help='', sources={'wish'}
                )]),
                ([CylcOption(
                    '-f', '--flammable', help='', sources={'rest'}
                )]),
                ([CylcOption(
                    '-n', '--non-flammable', help='', sources={'swim'}
                )]),
            ],
            [
                {OPTS: {'-i', '--inflammable'}},
                {OPTS: {'-f', '--flammable'}},
                {OPTS: {'-n', '--non-flammable'}}
            ],
            id='merge three argsets no overlap'
        ),
        param(
            [
                [
                    CylcOption(
                        '-m', '--morpeth', help='', sources={'stop'}),
                    CylcOption(
                        '-r', '--redesdale', help='', sources={'stop'}),
                ],
                [
                    CylcOption(
                        '-b', '--byker', help='', sources={'walk'}),
                    CylcOption(
                        '-r', '--roxborough', help='', sources={'walk'}),
                ],
                [
                    CylcOption(
                        '-b', '--bellingham', help='', sources={'leap'}),
                ]
            ],
            [
                {OPTS: {'--bellingham'}},
                {OPTS: {'--roxborough'}},
                {OPTS: {'--redesdale'}},
                {OPTS: {'--byker'}},
                {OPTS: {'-m', '--morpeth'}}
            ],
            id='merge three overlapping argsets'
        ),
        param(
            [
                ([]),
                (
                    [
                        CylcOption(
                            '-c', '--campden', help='x', sources={'foo'})
                    ]
                )
            ],
            [
                {OPTS: {'-c', '--campden'}}
            ],
            id="empty list doesn't clear result"
        ),
    ]
)
def test_combine_options(inputs, expect):
    """It combines multiple input sets"""
    result = combine_options(*inputs)
    result_args = [i.opts for i in result]

    # Order of args irrelevent to test
    for option in expect:
        assert option[OPTS] in result_args


@pytest.mark.parametrize(
    'argv_before, kwargs, expect',
    [
        param(
            'vip myworkflow -f something -b something_else --baz',
            {
                'script_name': 'play',
                'workflow_id': 'myworkflow',
                'compound_script_opts': [
                    CylcOption('--foo', '-f'),
                    CylcOption('--bar', '-b', action='store'),
                    CylcOption('--baz', action='store_true'),
                ],
                'script_opts': [
                    CylcOption('--foo', '-f'),
                ]
            },
            'play myworkflow -f something',
            id='remove some opts'
        ),
        param(
            'vip myworkflow',
            {
                'script_name': 'play',
                'workflow_id': 'myworkflow',
                'compound_script_opts': [
                    CylcOption('--foo', '-f'),
                    CylcOption('--bar', '-b'),
                    CylcOption('--baz'),
                ],
                'script_opts': []
            },
            'play myworkflow',
            id='no opts to keep'
        ),
        param(
            'vip ./myworkflow --foo something',
            {
                'script_name': 'play',
                'workflow_id': 'myworkflow',
                'compound_script_opts': [
                    CylcOption('--foo', '-f')],
                'script_opts': [
                    CylcOption('--foo', '-f'),
                ],
                'source': './myworkflow',
            },
            'play --foo something myworkflow',
            id='replace path'
        ),
        param(
            'vip --foo something',
            {
                'script_name': 'play',
                'workflow_id': 'myworkflow',
                'compound_script_opts': [
                    CylcOption('--foo', '-f')],
                'script_opts': [
                    CylcOption('--foo', '-f'),
                ],
                'source': './myworkflow',
            },
            'play --foo something myworkflow',
            id='no path given'
        ),
        param(
            'vip -n myworkflow --no-run-name',
            {
                'script_name': 'play',
                'workflow_id': 'myworkflow',
                'compound_script_opts': [
                    CylcOption('--workflow-name', '-n'),
                    CylcOption('--no-run-name'),
                ],
                'script_opts': [
                    CylcOption('--not-used'),
                ]
            },
            'play myworkflow',
            id='workflow-id-added'
        ),
    ]
)
def test_cleanup_sysargv(
    monkeypatch: pytest.MonkeyPatch,
    argv_before: str,
    kwargs: dict,
    expect: str
):
    """It replaces the contents of sysargv with Cylc Play argv items.
    """
    # Fake up sys.argv: for this test.
    dummy_cylc_path = '/pathto/my/cylc/bin/cylc'
    monkeypatch.setattr(
        sys, 'argv', [dummy_cylc_path, *shlex.split(argv_before)]
    )
    # Fake options too:
    opts = SimpleNamespace(**{
        i.dest: i for i in kwargs['compound_script_opts']
    })

    kwargs.update({'options': opts})
    if not kwargs.get('source', None):
        kwargs.update({'source': ''})

    # Test the script:
    cleanup_sysargv(**kwargs)
    assert sys.argv == [dummy_cylc_path, *shlex.split(expect)]


@pytest.mark.parametrize(
    'sysargs, opts, expect', (
        param(
            # Test for https://github.com/cylc/cylc-flow/issues/5905
            '--no-run-name --workflow-name=name',
            [
                get_option_by_name(INSTALL_OPTIONS, 'no_run_name'),
                get_option_by_name(INSTALL_OPTIONS, 'workflow_name'),
            ],
            [],
            id='--workflow-name=name'
        ),
        param(
            '--foo something',
            [],
            ['--foo', 'something'],
            id='no-opts-removed'
        ),
        param(
            '',
            [
                CylcOption('--foo', action='store'),
            ],
            [],
            id='Null-check'
        ),
        param(
            '''--keep1 --keep2 42 --keep3=Hi
            --throw1 --throw2 84 --throw3=There''',
            [
                CylcOption('--throw1', action='store_true'),
                CylcOption('--throw2', action='store'),
                CylcOption('--throw3', action='store'),
            ],
            ['--keep1', '--keep2', '42', '--keep3=Hi'],
            id='complex'
        ),
        param(
            "--foo '--foo=42' --bar='--foo=94' --baz '--foo 26'",
            [
                CylcOption('--foo', action='append'),
            ],
            ["--bar=--foo=94", "--baz", "--foo 26"],
            id="fiendish"
        ),
        param(
            "--foo 1 --fool 2",
            [
                CylcOption('--foo', action='store'),
            ],
            ["--fool", "2"],
            id="substring"
        ),
        param(
            "-v -v -x",
            [
                CylcOption('-v', action='count', dest='verbosity'),
            ],
            ['-x'],
            id="remove-multiple"
        ),
        param(
            "-f --bar",
            [
                CylcOption('--foo', '-f', action='count', dest='bar'),
            ],
            ['--bar'],
            id="short-n-long"
        ),
        param(
            "cylc frobnicate --quiet jbloggs --dir run1 jdoe",
            [
                CylcOption(
                    '--quiet', action='decrement', dest='verbosity'
                ),
                CylcOption('--dir', action='store'),
            ],
            ['cylc', 'frobnicate', 'jbloggs', 'jdoe'],
            id="non-typed-opt"
        )
    )
)
def test_filter_sysargv(
    sysargs: str, opts: List[CylcOption], expect: List[str]
):
    """It returns the subset of sys.argv that we ask for."""
    assert filter_sysargv(shlex.split(sysargs), *opts) == expect


class TestCylcOption():
    @staticmethod
    def test_init():
        opts = ['--foo', '-f']
        attrs = {'metavar': 'FOO'}
        sources = {'touch'}
        useif = 'hello'

        result = CylcOption(*opts, sources=sources, useif=useif, **attrs)

        assert result.opts == set(opts)
        assert result.attrs == attrs
        assert result.sources == sources
        assert result.useif == useif

    @staticmethod
    @pytest.mark.parametrize(
        'first, second, expect',
        (
            param(
                CylcOption('--foo', '-f', sources={'touch'}, useif='hello'),
                CylcOption('--foo', '-f', sources={'touch'}, useif='hello'),
                True,
                id='Totally the same'
            ),
            param(
                CylcOption('--foo', '-f', sources={'touch'}, useif='hello'),
                CylcOption('--foo', '-f', sources={'wibble'}, useif='byee'),
                True,
                id='Differing extras'
            ),
            param(
                CylcOption('-f', sources={'touch'}, useif='hello'),
                CylcOption('--foo', '-f', sources={'wibble'}, useif='byee'),
                False,
                id='Not equal opts'
            ),
        )
    )
    def test_match(
        first: CylcOption, second: CylcOption, expect: bool
    ):
        assert first.match(second) == expect

    @staticmethod
    @pytest.mark.parametrize(
        'first, second, expect',
        (
            param(
                ['--foo', '-f'],
                ['--foo', '-f'],
                {'--foo', '-f'},
                id='Totally the same'),
            param(
                ['--foo', '-f'],
                ['--foolish', '-f'],
                {'-f'},
                id='Some overlap'),
            param(
                ['--foo', '-f'],
                ['--bar', '-b'],
                set(),
                id='No overlap'),
        )
    )
    def test___and__(first, second, expect):
        first = CylcOption(*first)
        second = CylcOption(*second)
        assert first & second == expect

    @staticmethod
    @pytest.mark.parametrize(
        'first, second, expect',
        (
            param(
                ['--foo', '-f'],
                ['--foo', '-f'],
                set(),
                id='Totally the same'),
            param(
                ['--foo', '-f'],
                ['--foolish', '-f'],
                {'--foo'},
                id='Some overlap'),
            param(
                ['--foolish', '-f'],
                ['--foo', '-f'],
                {'--foolish'},
                id='Some overlap not commuting'),
            param(
                ['--foo', '-f'],
                ['--bar', '-b'],
                {'--foo', '-f'},
                id='No overlap'),
        )
    )
    def test___sub__(first, second, expect):
        first = CylcOption(*first)
        second = CylcOption(*second)
        assert first - second == expect

    @staticmethod
    def test__in_list():
        """It is in a list."""
        first = CylcOption('--foo')
        second = CylcOption('--foo')
        third = CylcOption('--bar')
        assert first._in_list([second, third]) is True
