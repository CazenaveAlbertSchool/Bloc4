"""
Génère un modèle ResNet18 non entraîné (poids aléatoires) sauvegardé en TorchScript.

Usage depuis la racine du projet :
    python -m ml.create_dummy_model

Ou depuis le conteneur API :
    docker compose exec api python -m ml.create_dummy_model

Le fichier produit (ml/dummy_model.pt) peut être utilisé pour valider
le pipeline de serving avant d'avoir un vrai modèle entraîné.
"""

import os
import torch
import torch.nn as nn
import torchvision.models as models

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "dummy_model.pt")


def create_dummy_model(output_path: str = OUTPUT_PATH) -> str:
    model = models.resnet18(weights=None)
    model.fc = nn.Linear(model.fc.in_features, 2)
    model.eval()
    example = torch.randn(1, 3, 224, 224)
    traced = torch.jit.trace(model, example)
    traced.save(output_path)
    print(f"Dummy model saved to {output_path}")
    return output_path


if __name__ == "__main__":
    create_dummy_model()
