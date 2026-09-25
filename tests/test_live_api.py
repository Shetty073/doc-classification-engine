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
        ref_id = f"REF_TEST_{int(time.time())}"

        # 3. Test POST /upload with PDF (GSTR-3B)
        print(f"3. Testing POST /upload with PDF (Set_4_GSTR3B_July_2025.pdf) for {ref_id}...")
        with open("sample_dataset/Set_4_GSTR3B_July_2025.pdf", "rb") as f:
            pdf_res = client.post(
                "/upload",
                headers=auth_headers,
                data={"reference_id": ref_id},
                files={"file": ("Set_4_GSTR3B_July_2025.pdf", f, "application/pdf")},
            )
        assert pdf_res.status_code == 202, f"PDF upload failed: {pdf_res.text}"
        pdf_data = pdf_res.json()
        pdf_doc_id = pdf_data["document_id"]
        assert pdf_data["status"] == "PENDING"
        print(f"   -> OK! PDF uploaded: doc_id={pdf_doc_id}, status=PENDING")

        # 4. Test POST /upload with Image (pan1.png)
        print("4. Testing POST /upload with Image (pan1.png)...")
        with open("sample_dataset/pan1.png", "rb") as f:
            img_res = client.post(
                "/upload",
                headers=auth_headers,
                data={"reference_id": ref_id},
                files={"file": ("pan1.png", f, "image/png")},
            )
        assert img_res.status_code == 202, f"Image upload failed: {img_res.text}"
        img_data = img_res.json()
        img_doc_id = img_data["document_id"]
        assert img_data["status"] == "PENDING"
        print(f"   -> OK! Image uploaded: doc_id={img_doc_id}, status=PENDING")

        # 5. Test POST /upload with UNKNOWN document (sample_electricity_bill.pdf)
        print("5. Testing POST /upload with UNKNOWN document (sample_electricity_bill.pdf)...")
        with open("tests/fixtures/sample_electricity_bill.pdf", "rb") as f:
            unk_res = client.post(
                "/upload",
                headers=auth_headers,
                data={"reference_id": ref_id},
                files={"file": ("sample_electricity_bill.pdf", f, "application/pdf")},
            )
        assert unk_res.status_code == 202, f"Unknown doc upload failed: {unk_res.text}"
        unk_data = unk_res.json()
        unk_doc_id = unk_data["document_id"]
        assert unk_data["status"] == "PENDING"
        print(f"   -> OK! Unknown doc uploaded: doc_id={unk_doc_id}, status=PENDING")

        # 6. Wait for ARQ worker to process all 3 documents
        print("6. Polling GET /documents/{ref_id}/status for worker completion...")
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

        # 7. Test GET /documents/{ref_id}
        print("7. Testing GET /documents/{ref_id} (completed list)...")
        docs_res = client.get(f"/documents/{ref_id}", headers=auth_headers)
        assert docs_res.status_code == 200
        completed_docs = docs_res.json()
        assert len(completed_docs) == 3

        doc_map = {d["document_id"]: d for d in completed_docs}

        # Verify GSTR
        gstr_doc = doc_map[pdf_doc_id]
        print(f"   - GSTR PDF doc: Category={gstr_doc['category']}, Score={gstr_doc['confidence_score']}/100, Guess={gstr_doc['guess']}")
        assert gstr_doc["category"] == "GST_RETURN"
        assert 1 <= gstr_doc["confidence_score"] <= 100

        # Verify PAN
        pan_doc = doc_map[img_doc_id]
        print(f"   - PAN Image doc: Category={pan_doc['category']}, Score={pan_doc['confidence_score']}/100, Guess={pan_doc['guess']}")
        assert pan_doc["category"] == "PAN_CARD"
        assert 1 <= pan_doc["confidence_score"] <= 100

        # Verify UNKNOWN document with guess and score (1 to 100)
        unk_doc = doc_map[unk_doc_id]
        print(f"   - UNKNOWN doc: Category={unk_doc['category']}, Score={unk_doc['confidence_score']}/100, Guess={unk_doc['guess']}")
        assert unk_doc["category"] == "UNKNOWN"
        assert 1 <= unk_doc["confidence_score"] <= 100
        assert unk_doc["guess"] is not None and len(unk_doc["guess"]) > 0
        assert "Electricity" in unk_doc["guess"] or "Utility" in unk_doc["guess"]
        print("   -> OK! UNKNOWN document correctly returned best guess and confidence score (1 to 100).")

        # 8. Test secure download
        print("8. Testing secure download GET /documents/download/{doc_id}...")
        download_url = doc_map[pdf_doc_id]["document_url"]
        dl_res = client.get(download_url, headers=auth_headers)
        assert dl_res.status_code == 200
        assert len(dl_res.content) > 100
        print(f"   -> OK! Download verified (downloaded {len(dl_res.content)} bytes).")

        print("\n==========================================")
        print("SUCCESS: ALL END-TO-END BANKING API TESTS PASSED!")
        print("==========================================")


if __name__ == "__main__":
    run_live_tests()
