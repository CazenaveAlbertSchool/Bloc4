import os, io, random
from typing import List, Tuple
import boto3, psycopg2
from PIL import Image
import torchvision.transforms as T
from torch.utils.data import Dataset, random_split

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://plants:plants@postgres:5432/plants")
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "http://minio:9000")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "minio")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "minio12345")
S3_BUCKET = os.getenv("S3_BUCKET", "plants")

def _parse_s3_uri(uri: str):
    assert uri.startswith("s3://")
    bucket_key = uri[len("s3://"):]
    parts = bucket_key.split("/", 1)
    bucket = parts[0]
    key = parts[1] if len(parts) > 1 else ""
    return bucket, key

def fetch_manifest() -> List[Tuple[str,int]]:
    # returns list of (s3_uri, label_idx)
    with psycopg2.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute("SELECT url_s3, label FROM plants_data WHERE url_s3 IS NOT NULL")
        rows = cur.fetchall()
    label_map = {"grass":0, "dandelion":1}
    out = []
    for uri, label in rows:
        if not uri or label not in label_map:
            continue
        out.append((uri, label_map[label]))
    random.shuffle(out)
    return out

class S3ImageDataset(Dataset):
    def __init__(self, items, transform=None):
        self.items = items
        self.transform = transform
        self.s3 = boto3.client(
            "s3",
            endpoint_url=S3_ENDPOINT_URL,
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        )

    def __len__(self):
        return len(self.items)

    def __getitem__(self, idx):
        uri, y = self.items[idx]
        bucket, key = _parse_s3_uri(uri)
        obj = self.s3.get_object(Bucket=bucket, Key=key)
        img = Image.open(io.BytesIO(obj["Body"].read())).convert("RGB")
        if self.transform:
            img = self.transform(img)
        return img, y
