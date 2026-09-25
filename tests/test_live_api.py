import time
import httpx

BASE_URL = "http://127.0.0.1:8000"


def run_live_tests():
    with httpx.Client(base_url=BASE_URL, timeout=60.0) as client:
        # 1. Test Health & Security Headers
        print("1. Testing GET /health...")
        health_res = client.get("/health")
        assert health_res.status_code == 200, f"Health check failed: {health_res.text}"
        headers = health_res.headers
        assert "Strict-Transport-Security" in headers
        assert headers.get("X-Content-Type-Options") == "nosniff"
        assert headers.get("X-Frame-Options") == "DENY"
        assert "Content-Security-Policy" in headers
        print("   -> OK! Health healthy and strict security headers verified.")

        # 2. Test POST /token (Authentication)
        print("2. Testing POST /token...")
        token_res = client.post(
            "/token",
            data={"username": "admin", "password": "admin_secure_pass123"},
        )
        assert token_res.status_code == 200, f"Token failed: {token_res.text}"
        token_data = token_res.json()
        access_token = token_data["access_token"]
        assert token_data["token_type"] == "bearer"
        print("   -> OK! JWT token acquired successfully.")

        auth_headers = {"Authorization": f"Bearer {access_token}"}
        ref_id = f"REF_TEST_ENT_{int(time.time())}"

        # 3. Test POST /upload-batch (Batch Ingestion)
        print(f"3. Testing POST /upload-batch with 2 files for {ref_id}...")
        with open("sample_dataset/Set_4_GSTR3B_July_2025.pdf", "rb") as f1, open("sample_dataset/pan1.png", "rb") as f2:
            batch_files = [
                ("files", ("Set_4_GSTR3B_July_2025.pdf", f1, "application/pdf")),
                ("files", ("pan1.png", f2, "image/png")),
            ]
            batch_res = client.post(
                "/upload-batch",
                headers=auth_headers,
                data={"reference_id": ref_id, "callback_url": "http://127.0.0.1:9999/test-webhook"},
                files=batch_files,
            )
        assert batch_res.status_code == 202, f"Batch upload failed: {batch_res.text}"
        batch_data = batch_res.json()
        assert batch_data["total_enqueued"] == 2
        batch_doc_ids = [d["document_id"] for d in batch_data["documents"]]
        print(f"   -> OK! Batch uploaded: 2 docs enqueued: {batch_doc_ids}")

        # 4. Test POST /upload with Single Utility Bill
        print("4. Testing POST /upload with Utility Bill (sample_electricity_bill.pdf)...")
        with open("tests/fixtures/sample_electricity_bill.pdf", "rb") as f3:
            single_res = client.post(
                "/upload",
                headers=auth_headers,
                data={"reference_id": ref_id},
                files={"file": ("sample_electricity_bill.pdf", f3, "application/pdf")},
            )
        assert single_res.status_code == 202, f"Single upload failed: {single_res.text}"
        single_doc_id = single_res.json()["document_id"]
        print(f"   -> OK! Single doc uploaded: {single_doc_id}")

        all_doc_ids = batch_doc_ids + [single_doc_id]

        # 5. Wait for ARQ worker to process all 3 documents
        print(f"5. Polling GET /documents/{ref_id}/status for worker completion (total 3 docs)...")
        completed = False
        status_summary = {}
        for attempt in range(40):
            time.sleep(2)
            status_res = client.get(f"/documents/{ref_id}/status", headers=auth_headers)
            assert status_res.status_code == 200
            status_summary = status_res.json()
            counts = status_summary["counts_by_status"]
            print(f"   [Poll #{attempt + 1}] Counts: {counts}")
            if counts.get("COMPLETED", 0) == 3:
                completed = True
                break

        assert completed, f"Documents did not complete within timeout. Status: {status_summary}"
        print("   -> OK! All 3 documents processed by ARQ worker.")

        # 6. Test GET /documents/{ref_id} (completed list & enterprise fields)
        print(f"6. Testing GET /documents/{ref_id} (checking metadata & quality scores)...")
        docs_res = client.get(f"/documents/{ref_id}", headers=auth_headers)
        assert docs_res.status_code == 200
        completed_docs = docs_res.json()
        assert len(completed_docs) == 3

        doc_map = {d["document_id"]: d for d in completed_docs}

        for doc_id, doc in doc_map.items():
            print(f"   - Doc ID: {doc_id}")
            print(f"     Category: {doc['category']}, Confidence: {doc['confidence_score']}/100")
            print(f"     Quality Score: {doc['quality_score']}/100, Issues: {doc['quality_issues']}")
            print(f"     Extracted Metadata: {doc['extracted_metadata']}")
            assert doc["quality_score"] is not None and 1 <= doc["quality_score"] <= 100
            assert isinstance(doc["extracted_metadata"], dict)

        # 7. Test secure download
        print("7. Testing secure download GET /documents/download/{doc_id}...")
        download_url = completed_docs[0]["document_url"]
        dl_res = client.get(download_url, headers=auth_headers)
        assert dl_res.status_code == 200
        assert len(dl_res.content) > 100
        print(f"   -> OK! Download verified ({len(dl_res.content)} bytes).")

        print("\n==========================================")
        print("SUCCESS: ALL ENTERPRISE BANKING API TESTS PASSED!")
        print("==========================================")


if __name__ == "__main__":
    run_live_tests()
