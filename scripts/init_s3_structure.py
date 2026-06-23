import boto3
from django.conf import settings
 
s3 = boto3.client(
    's3',
    aws_access_key_id     = settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key = settings.AWS_SECRET_ACCESS_KEY,
    region_name           = settings.AWS_S3_REGION_NAME,
)
 
bucket = settings.AWS_STORAGE_BUCKET_NAME
 
# Base folder structure — create placeholder files to establish folders
folders = [
    "media/.keep",
    "media/platform_users/.keep",
    "media/products/.keep",
]
 
for folder in folders:
    s3.put_object(
        Bucket=bucket,
        Key=folder,
        Body=b"",
        ContentType="application/octet-stream",
    )
    print(f"Created: s3://{bucket}/{folder}")
 
print("\\nBase S3 folder structure created.")
print("Company and user folders are created automatically when files are uploaded.")