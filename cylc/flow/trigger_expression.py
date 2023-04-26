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

from operator import and_, or_
import re
from typing import Any, Callable, Dict, List, TYPE_CHECKING, Union

from cylc.flow.exceptions import TriggerExpressionError
from cylc.flow.task_trigger import TaskTrigger


OperatorFunc = Callable[[Any, Any], bool]
TriggerType = Union[TaskTrigger, 'TriggerExpression']


REC_CONDITIONALS = re.compile("([&|()])")

OP_MAP: Dict[str, OperatorFunc] = {
    '&': and_,
    '|': or_
}


def listify_str_expression(expr: str) -> List[Union[str, list]]:
    """Convert a string containing a logical expression to a list

    Examples:
        >>> listify_str_expression('(foo)')
        ['foo']

        >>> listify_str_expression('foo & (bar | baz)')
        ['foo', '&', ['bar', '|', 'baz']]

        >>> listify_str_expression('(a&b)|(c|d)&(e|f)')
        [['a', '&', 'b'], '|', ['c', '|', 'd'], '&', ['e', '|', 'f']]

        >>> listify_str_expression('a & (b & c)')
        ['a', '&', ['b', '&', 'c']]

        >>> listify_str_expression('a & b')
        ['a', '&', 'b']

        >>> listify_str_expression('a & (b)')
        ['a', '&', 'b']

        >>> listify_str_expression('((foo)')
        Traceback (most recent call last):
        ValueError: ((foo)

        >>> listify_str_expression('(foo))')
        Traceback (most recent call last):
        ValueError: (foo))

    """
    expr = expr.replace("'", "\"")

    ret: List[Union[str, list]] = []
    stack: list = [ret]
    for item in REC_CONDITIONALS.split(expr):
        item = item.strip()
        if item and item not in {'(', ')'}:
            stack[-1].append(item)
        elif item == '(':
            stack[-1].append([])
            stack.append(stack[-1][-1])
        elif item == ')':
            stack.pop()
            if not stack:
                raise ValueError(expr)
            if isinstance(stack[-1][-1], list) and len(stack[-1][-1]) == 1:
                stack[-1][-1] = stack[-1][-1][0]
    if len(stack) > 1:
        raise ValueError(expr)
    return ret


# def populate_triggers(
#     expr_list: List[Union[str, list]],
#     triggers: Dict[str, 'TaskTrigger']
# ) -> List[Union['TaskTrigger', str]]:
#     # Walk down "expr_list" depth-first, and replace any items matching a
#     # key in "triggers" ("left" values) with the trigger.
#     ret = []
#     for i, item in enumerate(expr_list):
#         if isinstance(item, list):
#             ret.append(populate_triggers(item, triggers))
#         elif item in triggers:
#             ret.append(triggers[item])
#     return ret


class TriggerExpression:

    def __init__(
        self,
        expr: str,
        task_triggers: Dict[str, TaskTrigger]
    ) -> None:
        self.is_conditional = '|' in expr
        expr_list = listify_str_expression(expr)
        err_msg = "unexpected '{}' in trigger expression: " + expr
        try:
            self._first = self._process_trigger(expr_list[0], task_triggers)

            triggers: List[TriggerType] = []
            operators: List[OperatorFunc] = [and_]
            # operators: List[str] = ['&']
            for i, item in enumerate(expr_list[1:]):
                if i % 2 == 0:
                    try:
                        operators.append(OP_MAP[item])
                    except (KeyError, TypeError):
                        raise TriggerExpressionError(item)
                    # if item in OP_MAP:
                    #     operators.append(item)
                    # else:
                    #     err = True
                else:
                    new: Union['TaskTrigger', 'TriggerExpression']
                    triggers.append(self._process_trigger(item, task_triggers))
        except TriggerExpressionError as exc:
            raise TriggerExpressionError(err_msg.format(exc))

        if len(expr_list) % 2 == 0:
            raise TriggerExpressionError(err_msg.format(expr_list[-1]))

        self._others = zip(operators, triggers)
        self.is_conditional |= (or_ in operators)

    def _process_trigger(
        self, value: Union[str, list], task_triggers: Dict[str, 'TaskTrigger']
    ) -> TriggerType:
        stack = [value]
        while stack:
            item = stack.pop()
            if isinstance(item, list):
                stack.append(item)
            elif item in task_triggers:
                return task_triggers[value] # No no no!
            else:
                raise TriggerExpressionError(value)

    def __str__(self) -> str:
        ret = []
        for item in self._data[1:]:
            if isinstance(item, TriggerExpression):
                ret.append(f'({item})')
            elif isinstance(item, TaskTrigger):
                ret.append(str(item))
            else:
                ret.append(f' {item} ')
        return ''.join(ret)
