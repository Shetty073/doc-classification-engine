import pytest
from app.classifier import LLMClassifierService, prepare_document_images
from app.config import settings
from app.schemas import ClassificationResult


@pytest.fixture
def classifier():
    return LLMClassifierService()


def test_prepare_document_images_from_image():
    # Test with existing sample image
    images = prepare_document_images("sample_dataset/pan1.png", max_pages=1)
    assert len(images) == 1
    assert isinstance(images[0], str)
    assert len(images[0]) > 500  # Base64 string exists


def test_prepare_document_images_from_pdf():
    # Test with existing sample PDF
    images = prepare_document_images("sample_dataset/Set_4_GSTR3B_July_2025.pdf", max_pages=2)
    assert len(images) >= 1
    assert isinstance(images[0], str)
    assert len(images[0]) > 500


def test_prepare_document_images_nonexistent():
    images = prepare_document_images("nonexistent_file_path.pdf")
    assert images == []


def test_build_vlm_messages(classifier):
    fake_b64 = ["dGVzdF9pbWFnZV8x", "dGVzdF9pbWFnZV8y"]
    ocr_hint = "Unique Identification Authority of India 1234 5678 9012"
    messages = classifier.build_vlm_messages(fake_b64, ocr_text=ocr_hint)

    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert "PASSPORT" in messages[0]["content"]

    user_msg = messages[1]
    assert user_msg["role"] == "user"
    content = user_msg["content"]
    assert isinstance(content, list)
    assert content[0]["type"] == "text"
    assert "1234 5678 9012" in content[0]["text"]

    # Visual image payloads
    image_items = [c for c in content if c.get("type") == "image_url"]
    assert len(image_items) == 2
    assert image_items[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")


@pytest.mark.asyncio
async def test_classify_vlm_graceful_fallback_when_offline(classifier):
    # Tests that when VLM endpoint is unreachable, it gracefully triggers banking heuristics fallback
    ocr_text = "INCOME TAX DEPARTMENT GOVT OF INDIA PERMANENT ACCOUNT NUMBER CARD ABCDE1234F"
    result = await classifier.classify_vlm("sample_dataset/pan1.png", ocr_text=ocr_text)

    assert isinstance(result, ClassificationResult)
    assert result.category == "PAN_CARD"
    assert result.confidence_score >= 80


@pytest.mark.asyncio
async def test_unified_classify_dynamic_routing(classifier, monkeypatch):
    # 1. Test LLM mode routing
    monkeypatch.setattr(settings, "CLASSIFIER_MODE", "llm")
    ocr_text = "PASSPORT REPUBLIC OF INDIA TYPE P CODE IND"
    res_llm = await classifier.classify("sample_dataset/pan1.png", ocr_text=ocr_text)
    assert res_llm.category == "PASSPORT"

    # 2. Test VLM mode routing
    monkeypatch.setattr(settings, "CLASSIFIER_MODE", "vlm")
    res_vlm = await classifier.classify("sample_dataset/pan1.png", ocr_text=ocr_text)
    assert res_vlm.category == "PASSPORT"
