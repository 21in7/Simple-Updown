# r2_storage.py
# Module for interacting with Cloudflare R2 storage

import os
import boto3
from botocore.exceptions import ClientError
import hashlib

class R2Storage:
    def __init__(self):
        # Load credentials from environment variables
        self.endpoint_url = os.getenv('R2_ENDPOINT_URL')
        self.access_key_id = os.getenv('R2_ACCESS_KEY_ID')
        self.secret_access_key = os.getenv('R2_SECRET_ACCESS_KEY')
        self.bucket_name = os.getenv('R2_BUCKET_NAME')
        self.region = os.getenv('R2_REGION', 'auto')

        # Initialize S3 client for R2
        self.s3_client = boto3.client(
            's3',
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key_id,
            aws_secret_access_key=self.secret_access_key,
            region_name=self.region
        )

    def upload_file(self, file_path, object_name=None):
        # Upload a file to R2 bucket
        if object_name is None:
            object_name = os.path.basename(file_path)

        try:
            self.s3_client.upload_file(file_path, self.bucket_name, object_name)
            return True
        except ClientError as e:
            print(f"Error uploading file: {e}")
            return False
        
    def download_file(self, object_name, file_path):
        # Download a file from R2 bucket
        try:
            self.s3_client.download_file(self.bucket_name, object_name, file_path)
            return True
        except ClientError as e:
            print(f"Error downloading file: {e}")
            return False
        
    def get_file_stream(self, object_name):
        # Get file from R2 as a stream
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=object_name)
            return response['Body']
        except ClientError as e:
            print(f"Error getting file stream: {e}")
            return None
        
    def delete_file(self, object_name):
        # Delete a file from R2 bucket
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=object_name)
            return True
        except ClientError as e:
            print(f"Error deleting file: {e}")
            return False