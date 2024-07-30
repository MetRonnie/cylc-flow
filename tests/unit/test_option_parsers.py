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
    CylcOptionParser as COP,
    Options,
    OptionSettings,
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
    opts: Iterable[OptionSettings], name: str
) -> OptionSettings:
    """Get an OptionSettings object by name from a list of CylcOptions."""
    try:
        return next((x for x in opts if x.option.dest == name))
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
            [OptionSettings('-f', '--foo', sources={'do'})],
            [OptionSettings('-f', '--foo', sources={'dont'})],
            [OptionSettings('-f', '--foo', sources={'do', 'dont'})],
            id='identical arg lists unchanged',
        ),
        param(
            [OptionSettings('-f', '--foo', sources={'fall'})],
            [
                OptionSettings(
                    '-f', '--foolish', sources={'fold'}, help='not identical'
                )
            ],
            [
                OptionSettings('--foo', sources={'fall'}),
                OptionSettings(
                    '--foolish', sources={'fold'}, help='not identical'
                ),
            ],
            id='different arg lists lose shared names',
        ),
        param(
            [OptionSettings('-f', '--foo', sources={'cook'})],
            [
                OptionSettings(
                    '-f', '--foo',
                    sources={'bake'}, help='not identical', dest='foobius',
                )
            ],
            None,
            id='different args identical arg list cause exception',
        ),
        param(
            [OptionSettings('-g', '--goo', sources={'knit'})],
            [OptionSettings('-f', '--foo', sources={'feed'})],
            [
                OptionSettings('-g', '--goo', sources={'knit'}),
                OptionSettings('-f', '--foo', sources={'feed'}),
            ],
            id='all unrelated args added',
        ),
        param(
            [
                OptionSettings('-f', '--foo', sources={'work'}),
                OptionSettings('-r', '--redesdale', sources={'work'}),
            ],
            [
                OptionSettings('-f', '--foo', sources={'sink'}),
                OptionSettings('-b', '--buttered-peas', sources={'sink'}),
            ],
            [
                OptionSettings('-f', '--foo', sources={'work', 'sink'}),
                OptionSettings('-b', '--buttered-peas', sources={'sink'}),
                OptionSettings('-r', '--redesdale', sources={'work'}),
            ],
            id='do not repeat args',
        ),
        param(
            [OptionSettings('-f', '--foo', sources={'push'})],
            [],
            [OptionSettings('-f', '--foo', sources={'push'})],
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
                ([OptionSettings(
                    '-i', '--inflammable', help='', sources={'wish'}
                )]),
                ([OptionSettings(
                    '-f', '--flammable', help='', sources={'rest'}
                )]),
                ([OptionSettings(
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
                    OptionSettings(
                        '-m', '--morpeth', help='', sources={'stop'}),
                    OptionSettings(
                        '-r', '--redesdale', help='', sources={'stop'}),
                ],
                [
                    OptionSettings(
                        '-b', '--byker', help='', sources={'walk'}),
                    OptionSettings(
                        '-r', '--roxborough', help='', sources={'walk'}),
                ],
                [
                    OptionSettings(
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
                        OptionSettings(
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
                    OptionSettings('--foo', '-f'),
                    OptionSettings('--bar', '-b', action='store'),
                    OptionSettings('--baz', action='store_true'),
                ],
                'script_opts': [
                    OptionSettings('--foo', '-f'),
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
                    OptionSettings('--foo', '-f'),
                    OptionSettings('--bar', '-b'),
                    OptionSettings('--baz'),
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
                    OptionSettings('--foo', '-f')],
                'script_opts': [
                    OptionSettings('--foo', '-f'),
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
                    OptionSettings('--foo', '-f')],
                'script_opts': [
                    OptionSettings('--foo', '-f'),
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
                    OptionSettings('--workflow-name', '-n'),
                    OptionSettings('--no-run-name'),
                ],
                'script_opts': [
                    OptionSettings('--not-used'),
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
        i.option.dest: None for i in kwargs['compound_script_opts']
    })

    if not kwargs.get('source', None):
        kwargs.update({'source': ''})

    # Test the script:
    cleanup_sysargv(**kwargs, options=opts)
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
                OptionSettings('--foo', action='store'),
            ],
            [],
            id='Null-check'
        ),
        param(
            '''--keep1 --keep2 42 --keep3=Hi
            --throw1 --throw2 84 --throw3=There''',
            [
                OptionSettings('--throw1', action='store_true'),
                OptionSettings('--throw2', action='store'),
                OptionSettings('--throw3', action='store'),
            ],
            ['--keep1', '--keep2', '42', '--keep3=Hi'],
            id='complex'
        ),
        param(
            "--foo '--foo=42' --bar='--foo=94' --baz '--foo 26'",
            [
                OptionSettings('--foo', action='append'),
            ],
            ["--bar=--foo=94", "--baz", "--foo 26"],
            id="fiendish"
        ),
        param(
            "--foo 1 --fool 2",
            [
                OptionSettings('--foo', action='store'),
            ],
            ["--fool", "2"],
            id="substring"
        ),
        param(
            "-v -v -x",
            [
                OptionSettings('-v', action='count', dest='verbosity'),
            ],
            ['-x'],
            id="remove-multiple"
        ),
        param(
            "-f --bar",
            [
                OptionSettings('--foo', '-f', action='count', dest='bar'),
            ],
            ['--bar'],
            id="short-n-long"
        ),
        param(
            "cylc frobnicate --quiet jbloggs --dir run1 jdoe",
            [
                OptionSettings(
                    '--quiet', action='decrement', dest='verbosity'
                ),
                OptionSettings('--dir', action='store'),
            ],
            ['cylc', 'frobnicate', 'jbloggs', 'jdoe'],
            id="non-typed-opt"
        )
    )
)
def test_filter_sysargv(
    sysargs: str, opts: List[OptionSettings], expect: List[str]
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

        result = OptionSettings(*opts, sources=sources, useif=useif, **attrs)

        assert result.opts == set(opts)
        assert result.attrs == attrs
        assert result.sources == sources
        assert result.useif == useif
        assert result.opt_string == '--foo'

    @staticmethod
    @pytest.mark.parametrize(
        'first, second, expect',
        (
            param(
                OptionSettings('--foo', '-f', sources={'a'}, useif='hello'),
                OptionSettings('--foo', '-f', sources={'a'}, useif='hello'),
                True,
                id='Totally the same'
            ),
            param(
                OptionSettings('--foo', '-f', sources={'a'}, useif='hello'),
                OptionSettings('--foo', '-f', sources={'b'}, useif='byee'),
                True,
                id='Differing extras'
            ),
            param(
                OptionSettings('-f', sources={'a'}, useif='hello'),
                OptionSettings('--foo', '-f', sources={'b'}, useif='byee'),
                False,
                id='Not equal opts'
            ),
        )
    )
    def test___eq__(
        first: OptionSettings, second: OptionSettings, expect: bool
    ):
        assert (first == second) == expect

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
        first = OptionSettings(*first)
        second = OptionSettings(*second)
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
        first = OptionSettings(*first)
        second = OptionSettings(*second)
        assert first - second == expect

    @staticmethod
    def test__in_list():
        """It is in a list."""
        first = OptionSettings('--foo')
        second = OptionSettings('--foo')
        third = OptionSettings('--bar')
        assert first._in_list([second, third]) is True
