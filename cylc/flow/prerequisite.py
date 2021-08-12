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

from operator import and_, or_
import math
from typing import (
    Callable, Dict, List, NamedTuple, Optional, TYPE_CHECKING, Union
)

from cylc.flow.cycling.loader import get_point
from cylc.flow.data_messages_pb2 import (  # type: ignore
    PbPrerequisite,
    PbCondition,
)
from cylc.flow.exceptions import TriggerExpressionError
from cylc.flow.id import Tokens

if TYPE_CHECKING:
    from cylc.flow.cycling import PointBase


class MessageTuple(NamedTuple):
    """Subcomponent of a Prerequisite"""
    point: str
    name: str
    output: str


SatisfactionDict = Dict[MessageTuple, Union[str, bool]]


class ExpressionList:

    _op_map = {
        '&': and_,
        '|': or_
    }

    def __init__(self, expr: list, point: 'PointBase') -> None:
        from cylc.flow.task_trigger import TaskTrigger

        self.orig_list = expr
        self.operators: List[Optional[Callable[..., bool]]] = [None]
        self.items: List[Union[MessageTuple, 'ExpressionList']] = []
        self.flat_list: List[Union[MessageTuple, 'ExpressionList', str]] = []

        for i, val in enumerate(expr):
            if i % 2 == 0:
                if isinstance(val, TaskTrigger):
                    val = MessageTuple(
                        val.task_name, str(val.get_point(point)), val.output
                    )
                elif isinstance(val, list):  # noqa: SIM106
                    val = ExpressionList(val, point)
                else:
                    raise ValueError(
                        f"invalid item for expression: {val} "
                        "(even items should be TaskTrigger or nested list)"
                    )
                self.items.append(val)
            else:
                if val not in self._op_map:
                    raise ValueError(
                        f"invalid item for expression: {val} "
                        f"(odd items should be {' or '.join(self._op_map)})"
                    )
                self.operators.append(self._op_map[val])
            self.flat_list.append(val)

        self.zipped = list(zip(self.operators, self.items))
        self.is_conditional: bool = (or_ in self.operators)

    def evaluate(self, satisfied: SatisfactionDict) -> bool:
        _, item = self.zipped[0]
        ret = self._evaluate_item(item, satisfied)
        for operator, item in self.zipped[1:]:
            assert operator is not None  # -------------------------------------
            ret = operator(ret, self._evaluate_item(item, satisfied))
        return ret

    @staticmethod
    def _evaluate_item(
        item: Union[MessageTuple, 'ExpressionList'],
        satisfied: SatisfactionDict
    ) -> bool:
        if isinstance(item, ExpressionList):
            return item.evaluate(satisfied)
        return bool(satisfied[item])

    def __str__(self) -> str:
        ret = []
        for el in self.flat_list:
            if isinstance(el, MessageTuple):
                ret.append(Prerequisite.MESSAGE_TEMPLATE % el)
            elif isinstance(el, ExpressionList):
                ret.append(f'({el})')
            else:
                ret.append(f' {el} ')
        return ''.join(ret)

    def __repr__(self) -> str:
        return f"<{type(self).__name__}[ {self} ]>"


class Prerequisite:
    """The concrete result of an abstract logical trigger expression.

    A single TaskProxy can have multiple Prerequisites, all of which require
    satisfying. This corresponds to multiple tasks being dependencies of a task
    in Cylc graphs (e.g. `a => c`, `b => c`).

    But a single Prerequisite can also have multiple 'messages'
    (basically, subcomponents of a Prerequisite)
    corresponding to parenthesised expressions in Cylc graphs (e.g.
    `(a & b) => c` or `(a | b) => c`). For the OR operator (`|`), only one
    message has to be satisfied for the Prerequisite to be satisfied.
    """

    # Memory optimization - constrain possible attributes to this list.
    __slots__ = ["satisfied", "_all_satisfied",
                 "target_point_strings", "start_point",
                 "conditional_expression", "point"]

    # Extracts T from "foo.T succeeded" etc.
    SATISFIED_TEMPLATE = 'bool(self.satisfied[("%s", "%s", "%s")])'
    MESSAGE_TEMPLATE = r'%s/%s %s'

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
        self.conditional_expression: Optional[ExpressionList] = None

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

    # def _get_conditional_expression(expr: List[Any]) -> List[Any]:
    #     for message in self.satisfied:
    #         expr = expr.replace(self.MESSAGE_TEMPLATE % message,
    #                             self.SATISFIED_TEMPLATE % message)

    # def get_raw_conditional_expression(self) -> Optional[str]:
    #     """Return a representation of this prereq as a string.

    #     Returns None if this prerequisite is not a conditional one.

    #     """
    #     expr = self.conditional_expression
    #     if not expr:
    #         return None
    #     for message in self.satisfied:
    #         expr = expr.replace(self.SATISFIED_TEMPLATE % message,
    #                             self.MESSAGE_TEMPLATE % message)
    #     return expr

    def set_condition(self, expr: ExpressionList) -> None:
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
        # if '|' in expr:
        #     # Make a Python expression so we can eval() the logic.
        #     for message in self.satisfied:
        #         # Use '\b' in case one task name is a substring of another
        #         # and escape special chars ('.', timezone '+') in task IDs.
        #         expr = re.sub(
        #             fr"\b{re.escape(self.MESSAGE_TEMPLATE % message)}\b",
        #             self.SATISFIED_TEMPLATE % message,
        #             expr
        #         )
        #     self.conditional_expression = expr
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
        if self.conditional_expression:
            # Trigger expression with at least one '|': use eval.
            self._all_satisfied = self._conditional_is_satisfied()
        else:
            self._all_satisfied = all(self.satisfied.values())
        return self._all_satisfied

    # def _evaluate_conditional_expression(self) -> bool:
    #     ret: List[bool] = []
    #     for item in self.conditional_expression:
    #         if isinstance(item, MessageTuple):
    #             ret.append(bool(item in self.satisfied))
    #         elif isinstance(item, ExpressionList):
    #             ret.append(['(', cls._stringify_list(item, point), ')'])
    #         else:
    #             ret.append(item)
    #     return all(ret)

    def _conditional_is_satisfied(self) -> bool:
        """Evaluate the prerequisite's condition expression.

        Does not cache the result.

        """
        assert self.conditional_expression is not None  # ----------------------
        try:
            return self.conditional_expression.evaluate(self.satisfied)
        except (SyntaxError, ValueError) as exc:
            err_msg = str(exc)
            if str(exc).find("unexpected EOF") != -1:
                err_msg += (
                    " (could be unmatched parentheses in the graph string?)")
            raise TriggerExpressionError(
                '"%s":\n%s' % (str(self.conditional_expression), err_msg)
            )

    def satisfy_me(self, all_task_outputs):
        """Evaluate pre-requisite against known outputs.

        Updates cache with the evaluation result.

        """
        relevant_messages = all_task_outputs & set(self.satisfied)
        for message in relevant_messages:
            self.satisfied[message] = self.DEP_STATE_SATISFIED
            if self.conditional_expression is None:
                self._all_satisfied = all(self.satisfied.values())
            else:
                self._all_satisfied = self._conditional_is_satisfied()
        return relevant_messages

    def api_dump(self) -> Optional['PbPrerequisite']:
        """Return list of populated Protobuf data objects."""
        if not self.satisfied:
            return None
        if self.conditional_expression:
            temp = str(self.conditional_expression)
            # temp = temp.replace('|', ' | ')
            # temp = temp.replace('&', ' & ')
        else:
            for s_msg in self.satisfied:
                temp = self.MESSAGE_TEMPLATE % s_msg
        conds = []
        num_length = math.ceil(len(self.satisfied) / 10)
        for ind, message_tuple in enumerate(sorted(self.satisfied)):
            point, name = message_tuple[0:2]
            t_id = Tokens(cycle=str(point), task=name).relative_id
            char = 'c%.{0}d'.format(num_length) % ind
            c_msg = self.MESSAGE_TEMPLATE % message_tuple
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
            self._all_satisfied = self._conditional_is_satisfied()

    def set_not_satisfied(self) -> None:
        """Force this prerequisite into the un-satisfied state.

        State can be overridden by calling `self.satisfy_me`.

        """
        for message in self.satisfied:
            self.satisfied[message] = self.DEP_STATE_UNSATISFIED
        if not self.satisfied:
            self._all_satisfied = True
        elif self.conditional_expression is None:
            self._all_satisfied = False
        else:
            self._all_satisfied = self._conditional_is_satisfied()

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
