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

"""Functionality for expressing and evaluating logical triggers."""

import math
from typing import (
    Dict, List, NamedTuple, Optional, Set, TYPE_CHECKING, Union
)

from cylc.flow.cycling.loader import get_point
from cylc.flow.data_messages_pb2 import (  # type: ignore
    PbPrerequisite,
    PbCondition,
)
from cylc.flow.id import Tokens

if TYPE_CHECKING:
    from cylc.flow.cycling import PointBase
    from cylc.flow.task_trigger import TriggerExpression


class MessageTuple(NamedTuple):
    """Subcomponent of a Prerequisite"""
    point: str
    name: str
    output: str

    def __str__(self) -> str:
        return '{}/{} {}'.format(*self)


SatisfactionDict = Dict[MessageTuple, Union[str, bool]]


class Prerequisite:
    """The concrete result of an abstract logical trigger expression.

    A single TaskProxy can have multiple Prerequisites, all of which require
    satisfying. This corresponds to multiple tasks being dependencies of a task
    in Cylc graphs (e.g. `a => c`, `b => c`).

    But a single Prerequisite can also have multiple 'messages' (basically,
    subcomponents of a Prerequisite) corresponding to parenthesised
    expressions in Cylc graphs (e.g. `(a & b) => c` or `(a | b) => c`).
    For the OR operator (`|`), only one message has to be satisfied for the
    Prerequisite to be satisfied.
    """

    # Memory optimization - constrain possible attributes to this list.
    __slots__ = {
        "satisfied", "_all_satisfied", "target_point_strings", "start_point",
        "conditional_expression", "point"
    }

    DEP_STATE_SATISFIED = 'satisfied naturally'
    DEP_STATE_OVERRIDDEN = 'force satisfied'
    DEP_STATE_UNSATISFIED = False

    def __init__(
        self,
        point: 'PointBase',
        start_point: Optional['PointBase'] = None
    ) -> None:
        # The cycle point to which this prerequisite belongs.
        self.point: 'PointBase' = point

        # Start point for prerequisite validity.
        self.start_point: Optional['PointBase'] = start_point

        # List of cycle point strings that this prerequisite depends on.
        self.target_point_strings: List[str] = []

        # Dictionary of messages pertaining to this prerequisite.
        # {('point string', 'task name', 'output'): DEP_STATE_X, ...}
        self.satisfied: SatisfactionDict = {}

        # Expression present only when conditions are used.
        # '1/foo failed & 1/bar succeeded'
        self.conditional_expression: Optional['TriggerExpression'] = None

        # The cached state of this prerequisite:
        # * `None` (no cached state)
        # * `True` (prerequisite satisfied)
        # * `False` (prerequisite unsatisfied).
        self._all_satisfied: Optional[bool] = None

    def add(
        self,
        name: str,
        point: Union['PointBase', str],
        output: str,
        pre_initial: bool = False
    ) -> None:
        """Register an output with this prerequisite.

        Args:
            name: The name of the task to which the output pertains.
            point: The cycle point at which this dependent output
                should appear.
            output: String representing the output e.g. "succeeded".
            pre_initial: If this is a pre-initial dependency.

        """
        message = MessageTuple(str(point), name, output)

        # Add a new prerequisite as satisfied if pre-initial, else unsatisfied.
        if pre_initial:
            self.satisfied[message] = self.DEP_STATE_SATISFIED
        else:
            self.satisfied[message] = self.DEP_STATE_UNSATISFIED
        if self._all_satisfied is not None:
            self._all_satisfied = False
        if point and str(point) not in self.target_point_strings:
            self.target_point_strings.append(str(point))

    def set_condition(self, expr: 'TriggerExpression') -> None:
        """Set the conditional expression for this prerequisite.
        Resets the cached state (self._all_satisfied).

        Examples:
            # GH #3644 construct conditional expression when one task name
            # is a substring of another: foo | xfoo => bar.
            # Add 'foo' to the 'satisfied' dict before 'xfoo'.
            >>> preq = Prerequisite(1)
            >>> preq.satisfied = {
            ...    ('1', 'foo', 'succeeded'): False,
            ...    ('1', 'xfoo', 'succeeded'): False
            ... }
            >>> preq.set_condition("1/foo succeeded|1/xfoo succeeded")
            >>> expr = preq.conditional_expression
            >>> expr.split('|')  # doctest: +NORMALIZE_WHITESPACE
            ['bool(self.satisfied[("1", "foo", "succeeded")])',
            'bool(self.satisfied[("1", "xfoo", "succeeded")])']

        """
        self._all_satisfied = None
        if expr.is_conditional:
            self.conditional_expression = expr

    def is_satisfied(self) -> bool:
        """Return True if prerequisite is satisfied.

        Return cached state if present, else evaluate the prerequisite.

        """
        if self._all_satisfied is not None:
            return self._all_satisfied
        # Else no cached value.
        if self.satisfied == {}:
            # No prerequisites left after pre-initial simplification.
            return True
        self._all_satisfied = self._eval_is_satisfied()
        return self._all_satisfied

    def _eval_is_satisfied(self) -> bool:
        """Evaluate the prerequisite's (possibly conditional) expression.

        Does not cache the result.
        """
        if self.conditional_expression:
            # Trigger expression with at least one '|'
            return self.conditional_expression.evaluate(self.satisfied)
        return all(self.satisfied.values())

    def satisfy_me(
        self, all_task_outputs: Set[MessageTuple]
    ) -> Set[MessageTuple]:
        """Evaluate pre-requisite against known outputs.

        Updates cache with the evaluation result.

        """
        relevant_messages = all_task_outputs & set(self.satisfied)
        for message in relevant_messages:
            self.satisfied[message] = self.DEP_STATE_SATISFIED
            self._all_satisfied = self._eval_is_satisfied()
        return relevant_messages

    def api_dump(self) -> Optional['PbPrerequisite']:
        """Return list of populated Protobuf data objects."""
        if not self.satisfied:
            return None
        if self.conditional_expression:
            temp = str(self.conditional_expression)
        else:
            for s_msg in self.satisfied:
                temp = str(s_msg) # Eh??
        conds = []
        num_length = math.ceil(len(self.satisfied) / 10)
        for ind, message_tuple in enumerate(sorted(self.satisfied)):
            t_id = Tokens(
                cycle=message_tuple.point, task=message_tuple.name
            ).relative_id
            char = 'c%.{0}d'.format(num_length) % ind
            c_msg = str(message_tuple)
            c_val = self.satisfied[message_tuple]
            c_bool = bool(c_val)
            if c_bool is False:
                c_val = "unsatisfied"
            cond = PbCondition(
                task_proxy=t_id,
                expr_alias=char,
                req_state=message_tuple[2],
                satisfied=c_bool,
                message=c_val,
            )
            conds.append(cond)
            temp = temp.replace(c_msg, char)
        prereq_buf = PbPrerequisite(
            expression=temp,
            satisfied=self.is_satisfied(),
        )
        prereq_buf.conditions.extend(conds)
        prereq_buf.cycle_points.extend(self.target_point_strings)
        return prereq_buf

    def set_satisfied(self) -> None:
        """Force this prerequisite into the satisfied state.

        State can be overridden by calling `self.satisfy_me`.

        """
        for message in self.satisfied:
            if not self.satisfied[message]:
                self.satisfied[message] = self.DEP_STATE_OVERRIDDEN
        if self.conditional_expression is None:
            self._all_satisfied = True
        else:
            self._all_satisfied = (
                self.conditional_expression.evaluate(self.satisfied)
            )

    def set_not_satisfied(self) -> None:
        """Force this prerequisite into the un-satisfied state.

        State can be overridden by calling `self.satisfy_me`.

        """
        for message in self.satisfied:
            self.satisfied[message] = self.DEP_STATE_UNSATISFIED
        if self.satisfied == {}:
            self._all_satisfied = True
        elif self.conditional_expression is None:
            self._all_satisfied = False
        else:
            self._all_satisfied = (
                self.conditional_expression.evaluate(self.satisfied)
            )

    def get_target_points(self) -> List['PointBase']:
        """Return a list of cycle points target by each prerequisite,
        including each component of conditionals."""
        return [get_point(p) for p in self.target_point_strings]

    def get_resolved_dependencies(self) -> List[str]:
        """Return a list of satisfied dependencies.

        E.G: ['1/foo', '2/bar']

        """
        return [f'{point}/{name}' for
                (point, name, _), satisfied in self.satisfied.items() if
                satisfied == self.DEP_STATE_SATISFIED]
