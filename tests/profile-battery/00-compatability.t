#!/bin/bash
# THIS FILE IS PART OF THE CYLC SUITE ENGINE.
# Copyright (C) 2008-2017 NIWA
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
#-------------------------------------------------------------------------------
# Ensure that any changes to cylc haven't broken the profile-battery command
. $(dirname $0)/test_header
#-------------------------------------------------------------------------------
set_test_number 5
#-------------------------------------------------------------------------------
# Check the format of `cylc version --long`.
run_ok "${TEST_NAME_BASE}-cylc-version" python -c "
import os
import sys
os.chdir('${CYLC_DIR}/lib')
from cylc.profiling import get_cylc_directory
if get_cylc_directory() != '${CYLC_DIR}':
    sys.exit(1)
"
#-------------------------------------------------------------------------------
# Check for hello-world suite and that the cylc list command is still instated.
TEST_NAME="${TEST_NAME_BASE}-cylc-list-hello-world-suite"
run_ok "${TEST_NAME}" cylc list "${CYLC_DIR}/dev/suites/hello-world"
cmp_ok "${TEST_NAME}.stdout" "${TEST_NAME}.stdout" "hello-world"
#-------------------------------------------------------------------------------
# Check that the suites located in $CYLC_DIR/dev/suites are still valid.
TEST_NAME="${TEST_NAME_BASE}-dev-suites-validate"
mkdir "${TEST_LOG_DIR}/${TEST_NAME}" -p
broken=
for suite in $(find "${CYLC_DIR}/dev/suites" -name suite.rc)
do
    if ! cylc validate "${suite}" 2>&1 >/dev/null
    then
        broken="${suite}\n${broken}"
    fi
done
if [[ -z "${broken}" ]]
then
    ok "${TEST_NAME}"
else
    echo -en "The following suites failed validation:\n${broken}" \
        > "${TEST_NAME}.stderr"
    cp "${TEST_NAME}.stderr" "${TEST_LOG_DIR}/${TEST_NAME}.stderr"
    fail "${TEST_NAME}"
fi
#-------------------------------------------------------------------------------
# Run the test experiment.
TEST_NAME="${TEST_NAME_BASE}-run-test-experiment"
LOG_DIR="${TEST_LOG_DIR}/${TEST_NAME}"
mkdir "${LOG_DIR}" -p
RET_CODE=0
cylc profile-battery -e 'test' -v 'HEAD' --test \
    >"${LOG_DIR}.log" \
    2>"${LOG_DIR}.stderr" \
    || RET_CODE=$?
if [[ ${RET_CODE} == 0 ]]
then
    ok "${TEST_NAME}"
elif [[ ${RET_CODE} == 2 ]]
then
    echo "Test requires git repository." >&2
    skip 1
else
    fail "${TEST_NAME}"
    # Move/rename profiling files so they will be cat'ed out by travis-ci.
    PROF_FILES=($(sed 's/Profile files:\(.*\)/\1/' <<< \
        $(cat "${LOG_DIR}.stderr" | grep 'Profile files:')))
    for file_path in ${PROF_FILES[@]}; do
        file_prefix=$(basename ${file_path})
        profile_dir=$(dirname ${file_path})
        profile_files=($(find "${profile_dir}" -type f -name "${file_prefix}*" \
                2>/dev/null))
        for profile_file in ${profile_files[@]}; do
            mv "${profile_file}" "${LOG_DIR}/$(basename ${profile_file})-err"
        done
    done
    mv "${LOG_DIR}.log" "${LOG_DIR}.profile-battery-log-err"
fi