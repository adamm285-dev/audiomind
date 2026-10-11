"""
Verification script for custom trained 'Hey Anti' ONNX wake-word model.
Tests discrimination against near misses, other wake words, and conversational speech.
"""
import os
import sys

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

import asyncio
import numpy as np
import pytest
openwakeword = pytest.importorskip("openwakeword")
from openwakeword.model import Model
from desktop.model.train_hey_anti import synthesize_to_pcm

async def run_evaluation():
    print("=== Evaluating 'Hey Anti' ONNX Wake-Word Model ===")
    model_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "resources", "models", "hey_anti.onnx"))
    m = Model(wakeword_models=[model_path], inference_framework="onnx")

    test_cases = [
        ("Hey Anti", True),
        ("Hey Ante", True),
        ("Hey Auntie", True),
        ("hey anti", True),
        ("Hey Andy", False),
        ("Hey Annie", False),
        ("Hey Anthony", False),
        ("Hey Siri", False),
        ("Hey Google", False),
        ("Can you run the unit tests please?", False),
        ("What is the current build status?", False),
        ("We need to commit these changes.", False),
    ]

    passed = 0
    for phrase, is_target in test_cases:
        pcm = await synthesize_to_pcm(phrase, "en-US-JennyNeural")
        scores = []
        for i in range(0, len(pcm), 1280):
            chunk = pcm[i:i+1280]
            if len(chunk) < 1280:
                chunk = np.pad(chunk, (0, 1280 - len(chunk)))
            pred = m.predict(chunk)
            scores.append(pred["hey_anti"])
        
        max_score = max(scores) if scores else 0.0
        success = (max_score >= 0.5) if is_target else (max_score < 0.5)
        if success:
            passed += 1
        status = "PASS" if success else "FAIL"
        print(f"[{status}] Phrase: \"{phrase:<36}\" Target: {str(is_target):<5} Max Score: {max_score:.4f}")

    print(f"\nResults: {passed}/{len(test_cases)} Passed ({passed/len(test_cases)*100:.1f}%)")
    return passed == len(test_cases)

if __name__ == "__main__":
    asyncio.run(run_evaluation())
