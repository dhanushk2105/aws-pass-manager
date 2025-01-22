# lambda_function.py
import json
import boto3
import os
import cv2
import numpy as np
import base64
from cryptography.fernet import Fernet
from botocore.exceptions import ClientError

# Initialize AWS clients
s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['DYNAMODB_TABLE'])

def process_image(image_data, credentials):
    """Process image and hide credentials"""
    # Decode image
    image_bytes = base64.b64decode(image_data)
    nparr = np.frombuffer(image_bytes, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    # Generate encryption key
    key = Fernet.generate_key()
    cipher_suite = Fernet(key)
    
    # Encrypt credentials
    encrypted_data = cipher_suite.encrypt(json.dumps(credentials).encode())
    binary_data = ''.join(format(byte, '08b') for byte in encrypted_data)
    
    # Hide data in image
    data_index = 0
    for i in range(image.shape[0]):
        for j in range(image.shape[1]):
            for k in range(3):
                if data_index < len(binary_data):
                    image[i, j, k] = (image[i, j, k] & 254) | int(binary_data[data_index])
                    data_index += 1
    
    # Convert back to base64
    _, buffer = cv2.imencode('.png', image)
    processed_image = base64.b64encode(buffer).decode('utf-8')
    
    return processed_image, base64.b64encode(key).decode('utf-8')

def lambda_handler(event, context):
    """Main Lambda handler function"""
    try:
        http_method = event['httpMethod']
        path = event['path']
        
        # Route handling
        if http_method == 'POST' and path == '/credential':
            # Parse request body
            body = json.loads(event['body'])
            
            # Process image and credentials
            processed_image, key = process_image(
                body['image_data'],
                {
                    'username': body['username'],
                    'password': body['password']
                }
            )
            
            # Generate unique filename
            filename = f"images/{body['user_id']}/{os.urandom(16).hex()}.png"
            
            # Upload to S3
            s3.put_object(
                Bucket=os.environ['S3_BUCKET'],
                Key=filename,
                Body=base64.b64decode(processed_image),
                ContentType='image/png'
            )
            
            # Create DynamoDB record
            table.put_item(
                Item={
                    'id': os.urandom(16).hex(),
                    'user_id': body['user_id'],
                    'website_name': body['website_name'],
                    'website_url': body['website_url'],
                    's3_key': filename,
                    'encryption_key': key,
                    'notes': body.get('notes', ''),
                    'created_at': str(int(time.time())),
                }
            )
            
            return {
                'statusCode': 200,
                'body': json.dumps({'success': True})
            }
            
        elif http_method == 'GET' and path.startswith('/credential/'):
            credential_id = path.split('/')[-1]
            
            # Get credential from DynamoDB
            response = table.get_item(Key={'id': credential_id})
            credential = response['Item']
            
            # Get image from S3
            s3_response = s3.get_object(
                Bucket=os.environ['S3_BUCKET'],
                Key=credential['s3_key']
            )
            image_data = base64.b64encode(s3_response['Body'].read()).decode('utf-8')
            
            # Process and decrypt
            image_bytes = base64.b64decode(image_data)
            nparr = np.frombuffer(image_bytes, np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            # Extract data
            binary_data = ''
            for i in range(image.shape[0]):
                for j in range(image.shape[1]):
                    for k in range(3):
                        binary_data += str(image[i, j, k] & 1)
                        if len(binary_data) >= 1024:
                            break
                    if len(binary_data) >= 1024:
                        break
                if len(binary_data) >= 1024:
                    break
            
            # Decrypt
            bytes_data = int(binary_data[:1024], 2).to_bytes(128, byteorder='big')
            cipher_suite = Fernet(base64.b64decode(credential['encryption_key']))
            decrypted_data = cipher_suite.decrypt(bytes_data)
            credentials = json.loads(decrypted_data.decode('utf-8'))
            
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'success': True,
                    'password': credentials['password']
                })
            }
            
        elif http_method == 'DELETE' and path.startswith('/credential/'):
            credential_id = path.split('/')[-1]
            
            # Get credential
            response = table.get_item(Key={'id': credential_id})
            credential = response['Item']
            
            # Delete from S3
            s3.delete_object(
                Bucket=os.environ['S3_BUCKET'],
                Key=credential['s3_key']
            )
            
            # Delete from DynamoDB
            table.delete_item(Key={'id': credential_id})
            
            return {
                'statusCode': 200,
                'body': json.dumps({'success': True})
            }
            
        else:
            return {
                'statusCode': 404,
                'body': json.dumps({'error': 'Not found'})
            }
            
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }