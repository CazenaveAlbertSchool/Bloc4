import os, time, json
import torch
import torch.nn as nn
import torch.optim as optim
import torchvision.models as models
import torchvision.transforms as T
from torch.utils.data import DataLoader, random_split
from tqdm import tqdm
import mlflow
import boto3
from .dataset import fetch_manifest, S3ImageDataset

S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "http://minio:9000")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "minio")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "minio12345")
S3_BUCKET = os.getenv("S3_BUCKET", "plants")
ARTIFACT_PREFIX = os.getenv("ARTIFACT_PREFIX", "models/")

def make_dataloaders(batch_size=16, val_ratio=0.2):
    transform = T.Compose([
        T.Resize((224,224)),
        T.RandomHorizontalFlip(),
        T.ToTensor(),
        T.Normalize([0.485,0.456,0.406],[0.229,0.224,0.225]),
    ])
    items = fetch_manifest()
    if len(items) < 10:
        raise RuntimeError("Not enough images ingested yet. Please run ingestion first.")
    n_total = len(items)
    n_val = max(1, int(val_ratio * n_total))
    n_train = n_total - n_val
    ds = S3ImageDataset(items, transform=transform)
    train_ds, val_ds = random_split(ds, [n_train, n_val])
    return DataLoader(train_ds, batch_size=batch_size, shuffle=True, num_workers=0),            DataLoader(val_ds, batch_size=batch_size, shuffle=False, num_workers=0)

def build_model():
    m = models.resnet18(weights=models.ResNet18_Weights.DEFAULT)
    m.fc = nn.Linear(m.fc.in_features, 2)
    return m

def evaluate(model, dl, device):
    model.eval()
    correct = 0
    total = 0
    loss_sum = 0.0
    crit = nn.CrossEntropyLoss()
    with torch.no_grad():
        for x,y in dl:
            x,y = x.to(device), torch.tensor(y).to(device)
            logits = model(x)
            loss = crit(logits, y)
            loss_sum += loss.item() * x.size(0)
            pred = logits.argmax(dim=1)
            correct += (pred==y).sum().item()
            total += x.size(0)
    return loss_sum/total, correct/total

def train_one_run(epochs=3, lr=1e-3, batch_size=16):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    train_dl, val_dl = make_dataloaders(batch_size=batch_size)
    model = build_model().to(device)
    opt = optim.Adam(model.parameters(), lr=lr)
    crit = nn.CrossEntropyLoss()

    # Configure MLflow pour utiliser MinIO S3
    os.environ["MLFLOW_S3_ENDPOINT_URL"] = S3_ENDPOINT_URL
    os.environ["AWS_ACCESS_KEY_ID"] = AWS_ACCESS_KEY_ID
    os.environ["AWS_SECRET_ACCESS_KEY"] = AWS_SECRET_ACCESS_KEY
    
    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000"))
    mlflow.set_experiment("dandelion_vs_grass")
    with mlflow.start_run() as run:
        mlflow.log_params({"epochs": epochs, "lr": lr, "batch_size": batch_size})
        for ep in range(1, epochs+1):
            model.train()
            pbar = tqdm(train_dl, desc=f"Epoch {ep}/{epochs}")
            for x,y in pbar:
                x,y = x.to(device), torch.tensor(y).to(device)
                logits = model(x)
                loss = crit(logits, y)
                opt.zero_grad()
                loss.backward()
                opt.step()
                pbar.set_postfix(loss=loss.item())
            val_loss, val_acc = evaluate(model, val_dl, device)
            mlflow.log_metrics({"val_loss": val_loss, "val_acc": val_acc}, step=ep)

        # Save scripted model for portability
        model.eval()
        example = torch.randn(1,3,224,224).to(device)
        traced = torch.jit.trace(model, example)
        local_path = "/tmp/model_resnet18.pt"
        traced.save(local_path)
        mlflow.log_artifact(local_path, artifact_path="model")

        # Upload to MinIO S3
        s3 = boto3.client("s3",
            endpoint_url=S3_ENDPOINT_URL,
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY)
        key = f"{ARTIFACT_PREFIX}resnet18_{int(time.time())}.pt"
        s3.upload_file(local_path, S3_BUCKET, key)
        model_uri = f"s3://{S3_BUCKET}/{key}"
        # Save a small metadata JSON
        meta_path = "/tmp/model_meta.json"
        import json as _json
        with open(meta_path, "w") as f:
            _json.dump({"model_uri": model_uri, "val_acc": val_acc, "val_loss": val_loss}, f)
        mlflow.log_artifact(meta_path, artifact_path="model")

    return model_uri

if __name__ == "__main__":
    uri = train_one_run()
    print("MODEL_URI", uri)
