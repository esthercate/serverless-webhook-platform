
import json
import os
from datetime import datetime, timezone
from urllib.request import Request, urlopen

import boto3

dynamodb = boto3.resource("dynamodb")

TABLE_NAME = os.environ["TABLE_NAME"]
WEBHOOK_URL = os.environ["WEBHOOK_URL"]

table = dynamodb.Table(TABLE_NAME)

MAX_RECEIVE_COUNT = 5


def current_timestamp():
    return datetime.now(timezone.utc).isoformat()


def update_tracking_record(
    event_id,
    status,
    receive_count,
    http_status=None,
    error_message=None
):
    # Update delivery status and attempt details in DynamoDB.
    if not event_id:
        print("No eventId available; cannot update tracking record.")
        return

    expression = (
        "SET #status = :status, "
        "updatedAt = :updatedAt, "
        "attemptCount = :attemptCount"
    )

    names = {"#status": "status"}

    values = {
        ":status": status,
        ":updatedAt": current_timestamp(),
        ":attemptCount": receive_count
    }

    if http_status is not None:
        expression += ", lastHttpStatus = :httpStatus"
        values[":httpStatus"] = http_status

    if error_message is not None:
        expression += ", lastError = :lastError"
        values[":lastError"] = str(error_message)[:1000]

    table.update_item(
        Key={"eventId": event_id},
        UpdateExpression=expression,
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values
    )

    print(
        f"Updated event {event_id}: "
        f"status={status}, attemptCount={receive_count}"
    )


def lambda_handler(event, context):
    #Deliver SQS messages to the configured webhook endpoint.
    records = event.get("Records", [])

    for record in records:
        message_id = record.get("messageId", "unknown")
        attributes = record.get("attributes", {})

        try:
            receive_count = int(
                attributes.get("ApproximateReceiveCount", "1")
            )
        except (TypeError, ValueError):
            receive_count = 1

        event_id = None
        http_status = None

        try:
            webhook_event = json.loads(record["body"])
            event_id = webhook_event.get("eventId")

            if not event_id:
                raise ValueError("Message body is missing eventId")

            request_body = json.dumps(webhook_event).encode("utf-8")

            request = Request(
                WEBHOOK_URL,
                data=request_body,
                headers={"Content-Type": "application/json"},
                method="POST"
            )

            with urlopen(request, timeout=10) as response:
                http_status = response.status

            if not 200 <= http_status < 300:
                raise RuntimeError(
                    f"Webhook returned HTTP {http_status}"
                )

            update_tracking_record(
                event_id=event_id,
                status="DELIVERED",
                receive_count=receive_count,
                http_status=http_status
            )

            print(
                f"Delivered message {message_id}; "
                f"eventId={event_id}; HTTP {http_status}"
            )

        except Exception as error:
            print(
                f"Delivery failed for message {message_id}: {error}"
            )

            if event_id:
                failure_status = (
                    "FAILED"
                    if receive_count >= MAX_RECEIVE_COUNT
                    else "RETRYING"
                )

                try:
                    update_tracking_record(
                        event_id=event_id,
                        status=failure_status,
                        receive_count=receive_count,
                        http_status=http_status,
                        error_message=error
                    )
                except Exception as tracking_error:
                    print(
                        f"Tracking update also failed: "
                        f"{tracking_error}"
                    )

            # Re-raise so SQS can retry the message and eventually
            # route it to the configured dead-letter queue.
            raise

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "All events delivered"
        })
    }
