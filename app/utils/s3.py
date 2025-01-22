# app/utils/s3.py
import boto3
import uuid
from flask import current_app
import base64
import io

class S3Handler:
    def __init__(self):
        self.s3 = boto3.client(
            's3',
            aws_access_key_id=current_app.config['AWS_ACCESS_KEY_ID'],
            aws_secret_access_key=current_app.config['AWS_SECRET_ACCESS_KEY'],
            region_name=current_app.config['AWS_REGION']
        )
        self.bucket = current_app.config['S3_BUCKET']

    def upload_image(self, image_data):
        """Upload base64 image to S3"""
        try:
            # Generate unique filename
            filename = f"{str(uuid.uuid4())}.png"
            
            # Convert base64 to bytes
            image_bytes = base64.b64decode(image_data)
            
            # Upload to S3
            self.s3.upload_fileobj(
                io.BytesIO(image_bytes),
                self.bucket,
                filename,
                ExtraArgs={
                    'ContentType': 'image/png',
                    'ACL': 'private'
                }
            )
            
            # Generate presigned URL (valid for 1 hour)
            url = self.s3.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.bucket,
                    'Key': filename
                },
                ExpiresIn=3600
            )
            
            return filename

        except Exception as e:
            current_app.logger.error(f"S3 upload error: {str(e)}")
            raise

    def get_image_data(self, filename):
        """Get image from S3 and return as base64"""
        try:
            # Get object from S3
            response = self.s3.get_object(
                Bucket=self.bucket,
                Key=filename
            )
            
            # Read and encode image
            image_data = base64.b64encode(response['Body'].read()).decode('utf-8')
            return image_data
            
        except Exception as e:
            current_app.logger.error(f"S3 get error: {str(e)}")
            raise

    def delete_image(self, filename):
        """Delete image from S3"""
        try:
            self.s3.delete_object(
                Bucket=self.bucket,
                Key=filename
            )
        except Exception as e:
            current_app.logger.error(f"S3 delete error: {str(e)}")
            raise

    def get_presigned_url(self, filename):
        """Generate a presigned URL for the image"""
        try:
            url = self.s3.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.bucket,
                    'Key': filename
                },
                ExpiresIn=3600  # URL valid for 1 hour
            )
            return url
        except Exception as e:
            current_app.logger.error(f"S3 presigned URL error: {str(e)}")
            raise