#!/usr/bin/env python3
# THIS FILE IS PART OF THE CYLC SUITE ENGINE.
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
"""cylc jobs-submit JOB-LOG-ROOT [JOB-LOG-DIR ...]

(This command is for internal use.)

Submit task jobs to relevant job runners.
On a remote job host, this command reads the job files from STDIN.

"""
from cylc.flow.option_parsers import CylcOptionParser as COP
from cylc.flow.terminal import cli_function

INTERNAL = True


def get_option_parser():
    parser = COP(
        __doc__,
        argdoc=[
            ("JOB-LOG-ROOT", "The log/job sub-directory for the suite"),
            ("[JOB-LOG-DIR ...]", "A point/name/submit_num sub-directory"),
        ],
    )
    parser.add_option(
        "--remote-mode",
        help="Is this being run on a remote job host?",
        action="store_true",
        dest="remote_mode",
        default=False,
    )
    parser.add_option(
        "--utc-mode",
        help="(for remote mode) is the suite running in UTC mode?",
        action="store_true",
        dest="utc_mode",
        default=False,
    )

    return parser


@cli_function(get_option_parser)
def main(parser, opts, job_log_root, *job_log_dirs):
    """CLI main."""
    from cylc.flow.job_runner_mgr import JobRunnerManager
    JobRunnerManager().jobs_submit(
        job_log_root,
        job_log_dirs,
        remote_mode=opts.remote_mode,
        utc_mode=opts.utc_mode,
    )
