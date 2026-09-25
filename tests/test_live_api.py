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

        # 3. Test POST /upload with PDF (GSTR-3B)
        ref_id = f"REF_TEST_{int(time.time())}"
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

        # 5. Wait for ARQ worker to process both documents
        print("5. Polling GET /documents/{ref_id}/status for worker completion...")
        completed = False
        for attempt in range(30):
            time.sleep(2)
            status_res = client.get(f"/documents/{ref_id}/status", headers=auth_headers)
            assert status_res.status_code == 200
            status_summary = status_res.json()
            counts = status_summary["counts_by_status"]
            print(f"   [Poll #{attempt + 1}] Counts: {counts}")
            if counts.get("COMPLETED", 0) == 2:
                completed = True
                break

        assert completed, f"Documents did not complete within timeout. Status: {status_summary}"
        print("   -> OK! Both documents processed by ARQ worker.")

        # 6. Test GET /documents/{ref_id}
        print("6. Testing GET /documents/{ref_id} (completed list)...")
        docs_res = client.get(f"/documents/{ref_id}", headers=auth_headers)
        assert docs_res.status_code == 200
        completed_docs = docs_res.json()
        assert len(completed_docs) == 2

        doc_map = {d["document_id"]: d for d in completed_docs}
        print(f"   - PDF doc ({pdf_doc_id}) Category: {doc_map[pdf_doc_id]['category']}")
        print(f"   - Image doc ({img_doc_id}) Category: {doc_map[img_doc_id]['category']}")
        assert doc_map[pdf_doc_id]["category"] == "GST_RETURN"
        assert doc_map[img_doc_id]["category"] == "PAN_CARD"
        print("   -> OK! Exact categories verified against Indian Banking Taxonomy.")

        # 7. Test GET /documents/download/{doc_id}
        print("7. Testing secure download GET /documents/download/{doc_id}...")
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
