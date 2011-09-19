#!/bin/bash

# This script sends a message to NAGIOS 
EVENT=$1
SUITE=$2
TASK_ID=$3
MSG="$4"  # quotes required: message contains spaces
SERVICE=${TASK_ID%%%*}
TASK_TIME=${TASK_ID##*%}

#export MAIL_ADDRESS="b.miville@niwa.co.nz"

SYS="${USER##*_}"
case $SYS in
    oper)
        export NAGIOS=/usr/bin/nagios_submit
        export FACILITY=local0
    ;;
    *)
        export NAGIOS='echo nagios: '
        export FACILITY=local1
    ;;
esac

echo "EVENT: ${EVENT}, SUITE: ${SUITE}, TASK_ID: $TASK_ID, TASK: $SERVICE, TASK_TIME: $TASK_TIME,  MSG: $MSG"

case $EVENT in
    started)
        MESSAGE="$SERVICE started ($MSG)"
        $NAGIOS $SERVICE OK "$MESSAGE"
    ;;
    succeeded)
        MESSAGE="$SERVICE succeeded ($MSG)"
        $NAGIOS $SERVICE OK "$MESSAGE"
    ;;
    failed)
        MESSAGE="$SERVICE failed ($MSG)"
        $NAGIOS $SERVICE CRITICAL "$MESSAGE"
        #cylc email-alert ${EVENT} ${SUITE} ${TASK_ID} "${MESSAGE}"
    ;;
    submission_failed)
        MESSAGE="$SERVICE submission failed ($MSG)"
        $NAGIOS $SERVICE CRITICAL "$MESSAGE"
        #cylc email-alert ${EVENT} ${SUITE} ${TASK_ID} "${MESSAGE}"
    ;;
    warning)
        MESSAGE="$SERVICE has a Warning: $MSG"
        $NAGIOS $SERVICE WARNING "$MESSAGE"
        #cylc email-alert ${EVENT} ${SUITE} ${TASK_ID} "${MESSAGE}"
    ;;
    submission)
        MESSAGE="$SERVICE submission timeout ($MSG)"
        $NAGIOS $SERVICE CRITICAL "$MESSAGE"
        #cylc email-alert ${EVENT} ${SUITE} ${TASK_ID} "${MESSAGE}"
    ;;
    execution)
        MESSAGE="$SERVICE execution timeout ($MSG)"
        $NAGIOS $SERVICE CRITICAL "$MESSAGE"
        #cylc email-alert ${EVENT} ${SUITE} ${TASK_ID} "${MESSAGE}"
    ;;
    *)
        echo "NAGIOS not alerted."
    ;;
esac

exit 0
