#!/usr/bin/env python3
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
import pkg_resources
from types import SimpleNamespace

import pytest

from cylc.flow.scripts.cylc import iter_commands, execute_cmd


@pytest.fixture
def mocked_entry_points(monkeypatch):
    """Mock two entry points one good and one bad.

    The bad entry point should fail the way it would if dependencies were
    not installed for it.
    """
    def _resolve_bad(*args, **kwargs):
        raise ModuleNotFoundError('foo')

    def _require_bad(*args, **kwargs):
        raise pkg_resources.DistributionNotFound('bar', ['baz'])

    def _resolve_good(*args, **kwargs):
        def _execute(*args, **kwargs):
            return
        return _execute

    def _require_good(*args, **kwargs):
        return

    good = SimpleNamespace(
        name='bar',
        module_name='os.path',
        resolve=_resolve_good,
        require=_require_good,
    )
    bad = SimpleNamespace(
        name='bad',
        module_name='not.a.python.module',
        resolve=_resolve_bad,
        require=_require_bad,
    )

    monkeypatch.setattr(
        'cylc.flow.scripts.cylc.COMMANDS',
        {'good': good, 'bad': bad}
    )


def test_listing_commands_with_missing_dependencies(mocked_entry_points):
    """It should exclude commands with missing dependencies."""
    commands = list(iter_commands())
    assert len(commands) == 1
    assert commands[0][0] == 'good'


def test_executing_commands_with_missing_dependencies(
    mocked_entry_points,
    capcall,
    capsys,
):
    """It should fail with a warning for commands with missing dependencies."""
    # capture sys.exit calls
    capexit = capcall('sys.exit')

    # the "good" entry point should exit 0 (exit with no args)
    execute_cmd('good')
    assert capexit[0] == ((), {})
    assert capsys.readouterr().err == ''

    # the "bad" entry point should exit 1 with a warning to stderr
    capexit.clear()
    execute_cmd('bad')
    assert capexit[0] == ((1,), {})
    assert capsys.readouterr().err == (
        "cylc bad: The 'bar' distribution was not found and is"
        " required by baz\n"
    )
