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

def make_dataloaders_optimized(batch_size=8, val_ratio=0.25):
    """
    Optimisations:
    - Data augmentation plus agressive pour le training
    - Transformations minimales pour la validation
    - Batch size réduit à 8 pour plus de stabilité
    - Val ratio à 25% pour avoir plus de données de validation
    """
    # Transformations pour l'entraînement avec augmentation agressive
    train_transform = T.Compose([
        T.Resize((256, 256)),
        T.RandomResizedCrop(224, scale=(0.8, 1.0)),
        T.RandomHorizontalFlip(p=0.5),
        T.RandomVerticalFlip(p=0.3),
        T.RandomRotation(degrees=20),
        T.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.3, hue=0.1),
        T.RandomGrayscale(p=0.1),
        T.ToTensor(),
        T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        T.RandomErasing(p=0.2),
    ])

    # Transformations pour la validation (minimales)
    val_transform = T.Compose([
        T.Resize((224, 224)),
        T.ToTensor(),
        T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])

    items = fetch_manifest()
    if len(items) < 10:
        raise RuntimeError("Not enough images ingested yet. Please run ingestion first.")

    n_total = len(items)
    n_val = max(1, int(val_ratio * n_total))
    n_train = n_total - n_val

    # Créer deux datasets avec des transformations différentes
    full_ds = S3ImageDataset(items, transform=None)
    train_indices, val_indices = torch.utils.data.random_split(
        range(len(items)), [n_train, n_val],
        generator=torch.Generator().manual_seed(42)
    )

    # Datasets avec transformations appropriées
    train_items = [items[i] for i in train_indices.indices]
    val_items = [items[i] for i in val_indices.indices]

    train_ds = S3ImageDataset(train_items, transform=train_transform)
    val_ds = S3ImageDataset(val_items, transform=val_transform)

    print(f"Dataset split: {n_train} train, {n_val} val")

    return (
        DataLoader(train_ds, batch_size=batch_size, shuffle=True, num_workers=0, drop_last=True),
        DataLoader(val_ds, batch_size=batch_size, shuffle=False, num_workers=0)
    )

def build_model_optimized():
    """
    Utilise ResNet18 pré-entraîné avec:
    - Freeze initial du backbone pour stabilité
    - Classifier personnalisé avec Dropout
    """
    model = models.resnet18(weights=models.ResNet18_Weights.DEFAULT)

    # Remplacer le classifier avec dropout pour régularisation
    num_ftrs = model.fc.in_features
    model.fc = nn.Sequential(
        nn.Dropout(0.3),
        nn.Linear(num_ftrs, 256),
        nn.ReLU(),
        nn.Dropout(0.2),
        nn.Linear(256, 2)
    )

    return model

def evaluate(model, dl, device):
    """Évaluation avec métriques détaillées"""
    model.eval()
    correct = 0
    total = 0
    loss_sum = 0.0
    crit = nn.CrossEntropyLoss()

    all_preds = []
    all_labels = []

    with torch.no_grad():
        for x, y in dl:
            x, y = x.to(device), torch.tensor(y).to(device)
            logits = model(x)
            loss = crit(logits, y)
            loss_sum += loss.item() * x.size(0)
            pred = logits.argmax(dim=1)
            correct += (pred == y).sum().item()
            total += x.size(0)

            all_preds.extend(pred.cpu().numpy())
            all_labels.extend(y.cpu().numpy())

    accuracy = correct / total
    avg_loss = loss_sum / total

    return avg_loss, accuracy

def train_one_run_optimized(epochs=25, lr=5e-4, batch_size=8, patience=7):
    """
    Training optimisé avec:
    - Plus d'epochs (25 au lieu de 3)
    - Learning rate adapté au fine-tuning (5e-4)
    - Batch size réduit (8)
    - Early stopping avec patience
    - Learning rate scheduling
    - Fine-tuning progressif (freeze/unfreeze)
    """
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")

    train_dl, val_dl = make_dataloaders_optimized(batch_size=batch_size)
    model = build_model_optimized().to(device)

    # Phase 1: Freeze backbone, train only classifier
    print("\n=== PHASE 1: Training classifier only (frozen backbone) ===")
    for param in model.parameters():
        param.requires_grad = False
    for param in model.fc.parameters():
        param.requires_grad = True

    # Optimizer AdamW avec weight decay
    optimizer = optim.AdamW(
        filter(lambda p: p.requires_grad, model.parameters()),
        lr=lr * 2,  # LR plus élevé pour la phase de warmup
        weight_decay=0.01
    )

    # Learning rate scheduler - ReduceLROnPlateau
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode='min', factor=0.5, patience=3
    )

    crit = nn.CrossEntropyLoss()

    # Configure MLflow
    os.environ["MLFLOW_S3_ENDPOINT_URL"] = S3_ENDPOINT_URL
    os.environ["AWS_ACCESS_KEY_ID"] = AWS_ACCESS_KEY_ID
    os.environ["AWS_SECRET_ACCESS_KEY"] = AWS_SECRET_ACCESS_KEY

    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000"))
    mlflow.set_experiment("dandelion_vs_grass")

    best_val_acc = 0.0
    best_val_loss = float('inf')
    patience_counter = 0

    with mlflow.start_run() as run:
        mlflow.log_params({
            "epochs": epochs,
            "lr": lr,
            "batch_size": batch_size,
            "optimizer": "AdamW",
            "architecture": "ResNet18_optimized",
            "patience": patience,
            "training_strategy": "progressive_fine_tuning"
        })

        # Phase 1: Warmup (5 epochs avec classifier seulement)
        warmup_epochs = 5
        for ep in range(1, warmup_epochs + 1):
            model.train()
            train_loss = 0.0
            pbar = tqdm(train_dl, desc=f"Warmup Epoch {ep}/{warmup_epochs}")

            for x, y in pbar:
                x, y = x.to(device), torch.tensor(y).to(device)
                logits = model(x)
                loss = crit(logits, y)

                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

                train_loss += loss.item()
                pbar.set_postfix(loss=loss.item())

            val_loss, val_acc = evaluate(model, val_dl, device)
            scheduler.step(val_loss)

            mlflow.log_metrics({
                "train_loss": train_loss / len(train_dl),
                "val_loss": val_loss,
                "val_acc": val_acc,
                "learning_rate": optimizer.param_groups[0]['lr']
            }, step=ep)

            print(f"Warmup Epoch {ep}: val_loss={val_loss:.4f}, val_acc={val_acc:.4f}")

            if val_acc > best_val_acc:
                best_val_acc = val_acc
                best_val_loss = val_loss

        # Phase 2: Unfreeze et fine-tune tout le modèle
        print("\n=== PHASE 2: Fine-tuning full model ===")
        for param in model.parameters():
            param.requires_grad = True

        # Nouvel optimizer avec LR plus bas pour le fine-tuning complet
        optimizer = optim.AdamW(
            model.parameters(),
            lr=lr,  # LR de base pour fine-tuning
            weight_decay=0.01
        )

        scheduler = optim.lr_scheduler.ReduceLROnPlateau(
            optimizer, mode='min', factor=0.5, patience=3
        )

        for ep in range(warmup_epochs + 1, epochs + 1):
            model.train()
            train_loss = 0.0
            pbar = tqdm(train_dl, desc=f"Fine-tune Epoch {ep}/{epochs}")

            for x, y in pbar:
                x, y = x.to(device), torch.tensor(y).to(device)
                logits = model(x)
                loss = crit(logits, y)

                optimizer.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
                optimizer.step()

                train_loss += loss.item()
                pbar.set_postfix(loss=loss.item())

            val_loss, val_acc = evaluate(model, val_dl, device)
            scheduler.step(val_loss)

            mlflow.log_metrics({
                "train_loss": train_loss / len(train_dl),
                "val_loss": val_loss,
                "val_acc": val_acc,
                "learning_rate": optimizer.param_groups[0]['lr']
            }, step=ep)

            print(f"Epoch {ep}: val_loss={val_loss:.4f}, val_acc={val_acc:.4f} | Best: {best_val_acc:.4f}")

            # Early stopping
            if val_acc > best_val_acc:
                best_val_acc = val_acc
                best_val_loss = val_loss
                patience_counter = 0
                print(f"✓ New best model! Accuracy: {best_val_acc:.4f}")
            else:
                patience_counter += 1
                if patience_counter >= patience:
                    print(f"Early stopping triggered after {ep} epochs")
                    break

        # Log final best metrics
        mlflow.log_metrics({
            "best_val_acc": best_val_acc,
            "best_val_loss": best_val_loss
        })

        # Save model
        model.eval()
        example = torch.randn(1, 3, 224, 224).to(device)
        traced = torch.jit.trace(model, example)
        local_path = "/tmp/model_resnet18_optimized.pt"
        traced.save(local_path)
        mlflow.log_artifact(local_path, artifact_path="model")

        # Upload to MinIO S3
        s3 = boto3.client("s3",
            endpoint_url=S3_ENDPOINT_URL,
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY)
        key = f"{ARTIFACT_PREFIX}resnet18_optimized_{int(time.time())}.pt"
        s3.upload_file(local_path, S3_BUCKET, key)
        model_uri = f"s3://{S3_BUCKET}/{key}"

        # Save metadata
        meta_path = "/tmp/model_meta.json"
        with open(meta_path, "w") as f:
            json.dump({
                "model_uri": model_uri,
                "val_acc": best_val_acc,
                "val_loss": best_val_loss,
                "architecture": "ResNet18_optimized",
                "training_strategy": "progressive_fine_tuning"
            }, f)
        mlflow.log_artifact(meta_path, artifact_path="model")

        print(f"\n=== TRAINING COMPLETE ===")
        print(f"Best Validation Accuracy: {best_val_acc*100:.2f}%")
        print(f"Best Validation Loss: {best_val_loss:.4f}")
        print(f"Model URI: {model_uri}")

    return model_uri

if __name__ == "__main__":
    uri = train_one_run_optimized()
    print("MODEL_URI", uri)
