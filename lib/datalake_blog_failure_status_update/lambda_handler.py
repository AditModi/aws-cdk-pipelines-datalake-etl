# Copyright 2021 Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
import boto3
import botocore
import os
import logging
import os.path
from datetime import datetime
import dateutil.tz


# Function for logger
def load_log_config():
    # Basic config. Replace with your own logging config if required
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    return root


# Logger initiation
logger = load_log_config()


def lambda_handler(event, context):
    # TODO implement
    print(event)
    print(event['Input'])

    print(event['Input']['execution_id'])
    print(event['Input']['taskresult']['Cause'])

    execution_id = event['Input']['execution_id']

    central = dateutil.tz.gettz('US/Central')
    now = datetime.now(tz=central)
    p_ingest_time = now.strftime('%m/%d/%Y %H:%M:%S')
    logger.info(p_ingest_time)

    status = 'FAILED'
    error_msg = event['Input']['taskresult']['Cause']
    # Time stamp for the stepfunction name
    p_stp_fn_time = now.strftime('%Y%m%d%H%M%S%f')
    # update table

    try:
        dynamo_client = boto3.resource('dynamodb')
        table = client.Table(os.environ['DYNAMODB_TABLE_NAME'])
        table.update_item(
            Key={
                'execution_id': execution_id
            },
            UpdateExpression='set joblast_updated_timestamp=:lut,job_latest_status=:sts,error_message=:emsg',
            ExpressionAttributeValues={
                ':sts': status,
                ':lut': p_stp_fn_time,
                ':emsg': error_msg
            },
            ReturnValues='UPDATED_NEW'
        )
    except botocore.exceptions.ClientError as error:
        logger.info('[ERROR] Step function client process failed:{}'.format(error))
        raise error
    except Exception as e:
        logger.info('[ERROR] Step function call failed:{}'.format(e))
        raise e

    return {
        'statusCode': 200,
        'body': json.dumps('Failure status update!')
    }