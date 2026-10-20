"""
Machine Learning Engine for VoiceOps
Provides ML-based classification to augment deterministic rule-based decisions
"""
import json
import pickle
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder
import logging

from app.config import DATA_DIR

logger = logging.getLogger(__name__)

class MLExceptionEngine:
    """ML-based exception classification engine"""

    def __init__(self, model_path: Optional[Path] = None):
        self.model_path = model_path or (DATA_DIR / "ml_model.pkl")
        self.vectorizer_path = self.model_path.parent / "tfidf_vectorizer.pkl"
        self.label_encoder_path = self.model_path.parent / "label_encoder.pkl"

        self.pipeline: Optional[Pipeline] = None
        self.label_encoder: Optional[LabelEncoder] = None
        self.is_trained = False

        # Try to load existing model
        self._load_model()

    def _load_model(self) -> bool:
        """Load pre-trained model from disk"""
        try:
            if self.model_path.exists() and self.vectorizer_path.exists() and self.label_encoder_path.exists():
                with open(self.model_path, 'rb') as f:
                    self.pipeline = pickle.load(f)
                with open(self.vectorizer_path, 'rb') as f:
                    # Vectorizer is part of pipeline in newer approach
                    pass
                with open(self.label_encoder_path, 'rb') as f:
                    self.label_encoder = pickle.load(f)
                self.is_trained = True
                logger.info("ML model loaded successfully")
                return True
        except Exception as e:
            logger.warning(f"Failed to load ML model: {e}")
            self.is_trained = False
        return False

    def _save_model(self):
        """Save model to disk"""
        try:
            self.model_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.model_path, 'wb') as f:
                pickle.dump(self.pipeline, f)
            with open(self.label_encoder_path, 'wb') as f:
                pickle.dump(self.label_encoder, f)
            logger.info("ML model saved successfully")
        except Exception as e:
            logger.error(f"Failed to save ML model: {e}")

    def train(self, cases: List[Dict[str, Any]]):
        """Train the ML model on historical case data"""
        try:
            # Prepare training data
            texts = []
            labels = []

            for case in cases:
                # Combine relevant text fields for feature extraction
                text = " ".join([
                    str(case.get('exception_text', '')),
                    str(case.get('expected_type', '')),
                    str(case.get('supporting_evidence', '')),
                    str(case.get('missing_fields', ''))
                ]).strip()

                if text and case.get('expected_type'):
                    texts.append(text.lower())
                    labels.append(case['expected_type'])

            if len(texts) < 10:  # Need minimum samples to train
                logger.warning(f"Insufficient training data: {len(texts)} samples")
                return False

            # Create and train pipeline
            self.pipeline = Pipeline([
                ('tfidf', TfidfVectorizer(max_features=1000, stop_words='english')),
                ('classifier', MultinomialNB())
            ])

            # Encode labels
            self.label_encoder = LabelEncoder()
            encoded_labels = self.label_encoder.fit_transform(labels)

            # Train the model
            self.pipeline.fit(texts, encoded_labels)
            self.is_trained = True

            # Save the model
            self._save_model()

            logger.info(f"ML model trained successfully on {len(texts)} samples")
            return True

        except Exception as e:
            logger.error(f"Failed to train ML model: {e}")
            self.is_trained = False
            return False

    def predict(self, case: Dict[str, Any]) -> Tuple[Optional[str], float]:
        """
        Predict exception type using ML model
        Returns: (predicted_exception_type, confidence_score)
        """
        if not self.is_trained or not self.pipeline:
            return None, 0.0

        try:
            # Prepare input text
            text = " ".join([
                str(case.get('exception_text', '')),
                str(case.get('expected_type', '')),
                str(case.get('supporting_evidence', '')),
                str(case.get('missing_fields', ''))
            ]).strip()

            if not text:
                return None, 0.0

            # Get prediction probabilities
            probabilities = self.pipeline.predict_proba([text.lower()])[0]
            max_prob_index = np.argmax(probabilities)
            confidence = float(probabilities[max_prob_index])

            # Decode label
            predicted_label = self.label_encoder.inverse_transform([max_prob_index])[0]

            return predicted_label, confidence

        except Exception as e:
            logger.error(f"ML prediction failed: {e}")
            return None, 0.0

    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the current model"""
        if not self.is_trained:
            return {"trained": False, "message": "Model not trained"}

        try:
            return {
                "trained": True,
                "classes": list(self.label_encoder.classes_) if self.label_encoder else [],
                "model_type": "MultinomialNB with TF-IDF features",
                "feature_count": len(self.pipeline.named_steps['tfidf'].get_feature_names_out()) if hasattr(self.pipeline.named_steps['tfidf'], 'get_feature_names_out') else 0
            }
        except Exception as e:
            logger.error(f"Failed to get model info: {e}")
            return {"trained": True, "error": str(e)}

# Global instance
ml_engine = MLExceptionEngine()