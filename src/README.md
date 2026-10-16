# Lambda Source Code

This directory contains the Python source code for the two AWS Lambda functions used in the Serverless Webhook Platform.

## Files

### `webhook_ingestion.py`

Responsible for:
- Validating incoming event data.
- Generating a unique event ID.
- Recording the event in DynamoDB with an initial `PENDING` status.
- Sending the event to the main SQS queue.
- Recording enqueue failures where possible.

### `webhook_delivery_worker.py`

Responsible for:
- Reading events delivered by the SQS event source mapping.
- Sending HTTP POST requests to the configured webhook endpoint.
- Updating delivery status and attempt details in DynamoDB.
- Raising processing errors so SQS can retry failed messages and route repeatedly failing messages to the configured dead-letter queue.

## Configuration

The functions use environment variables rather than hard-coded resource URLs.

**Ingestion function**
- `QUEUE_URL`
- `TABLE_NAME`

**Delivery worker**
- `WEBHOOK_URL`
- `TABLE_NAME`

Configure these variables in the AWS Lambda console when deploying the functions. Do not commit private endpoint URLs, credentials, or tokens.

## Deployment note

These files document the application source code. Deploying changes to these files does not automatically update the Lambda functions already deployed in AWS.