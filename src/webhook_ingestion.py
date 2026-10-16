
import json
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import boto3

sqs = boto3.client("sqs")
dynamodb = boto3.resource("dynamodb")

QUEUE_URL = os.environ["QUEUE_URL"]
TABLE_NAME = os.environ["TABLE_NAME"]

table = dynamodb.Table(TABLE_NAME)


def current_timestamp():
    return datetime.now(timezone.utc).isoformat()


def convert_floats_to_decimal(value):
    # Convert floats recursively for DynamoDB compatibility.
    if isinstance(value, float):
        return Decimal(str(value))

    if isinstance(value, dict):
        return {
            key: convert_floats_to_decimal(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [
            convert_floats_to_decimal(item)
            for item in value
        ]

    return value


def lambda_handler(event, context):
    # Validate, track, and enqueue an incoming event.
    if not isinstance(event, dict):
        return {
            "statusCode": 400,
            "body": json.dumps({
                "error": "Event must be a JSON object"
            })
        }

    event_type = event.get("eventType")
    payload = event.get("payload")

    if not isinstance(event_type, str) or not event_type.strip():
        return {
            "statusCode": 400,
            "body": json.dumps({
                "error": "eventType is required"
            })
        }

    if not isinstance(payload, dict):
        return {
            "statusCode": 400,
            "body": json.dumps({
                "error": "payload must be a JSON object"
            })
        }

    event_id = str(uuid.uuid4())
    timestamp = current_timestamp()

    message = {
        "eventId": event_id,
        "eventType": event_type,
        "payload": payload
    }

    # Record the event before enqueueing it.
    table.put_item(
        Item={
            "eventId": event_id,
            "eventType": event_type,
            "payload": convert_floats_to_decimal(payload),
            "status": "PENDING",
            "createdAt": timestamp,
            "updatedAt": timestamp,
            "attemptCount": 0
        }
    )

    try:
        response = sqs.send_message(
            QueueUrl=QUEUE_URL,
            MessageBody=json.dumps(message)
        )

    except Exception as error:
        # Track an enqueue failure if possible.
        try:
            table.update_item(
                Key={"eventId": event_id},
                UpdateExpression=(
                    "SET #status = :status, "
                    "updatedAt = :updatedAt, "
                    "lastError = :lastError"
                ),
                ExpressionAttributeNames={
                    "#status": "status"
                },
                ExpressionAttributeValues={
                    ":status": "ENQUEUE_FAILED",
                    ":updatedAt": current_timestamp(),
                    ":lastError": str(error)[:1000]
                }
            )
        except Exception as tracking_error:
            print(
                f"Could not update tracking record for "
                f"{event_id}: {tracking_error}"
            )

        print(f"Could not enqueue event {event_id}: {error}")

        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": "Could not queue event",
                "eventId": event_id
            })
        }

    print(f"Queued event {event_id}")

    return {
        "statusCode": 202,
        "body": json.dumps({
            "message": "Event accepted",
            "eventId": event_id,
            "sqsMessageId": response["MessageId"]
        })
    }
