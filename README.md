# crewai-agent-marketing

Agent **Marketing** — **Flow chủ trì** cuộc họp "Kế hoạch chiến dịch quý" với Sale và HR trên CrewAI AMP.

```
intake → propose (campaign_budget) → hỏi Sale (A2A) → hỏi HR (A2A) ─┬─ HR thiếu người → chuyển câu hỏi cho Sale → hỏi lại HR
                                                                  └─► finalize → người duyệt (HITL của AMP: email)
   duyệt → kết thúc · từ chối → kết thúc · "yêu cầu sửa: …" → đề xuất lại (tối đa 2 lần)
```

- Inputs `/kickoff`: `product`, `quarter`, `budget`, `goal` (đều có mặc định).
- Biến môi trường: `SALE_A2A_URL`, `SALE_A2A_TOKEN`, `SALE_A2A_AGENT`, `HR_A2A_URL`, `HR_A2A_TOKEN`, `HR_A2A_AGENT`. Trên AMP (gói Basic) Sale và HR chạy chung deployment [crewai-agent-team](https://github.com/fenixdo/crewai-agent-team): URL và **token của deployment đó**, `_AGENT` = slug A2A (`truong_phong_kinh_doanh`, `truong_phong_nhan_su`).
- Người duyệt trả lời: `duyệt` · `từ chối: lý do` · `yêu cầu sửa: góp ý` (ví dụ `yêu cầu sửa: giảm ngân sách 20%`). Câu trả lời được đọc bằng code.
- Kết quả có `transcript`: toàn bộ tin nhắn Marketing ↔ Sale ↔ HR ↔ người duyệt.
- LLM: **FakeLLM** theo kịch bản (`script.py`); đặt `MODEL` để dùng LLM thật.

```bash
uv sync --group dev && .venv/bin/pytest -q                   # test offline (Sale/HR giả lập)
python ../../scripts/local_stack.py                           # họp thật trên máy: Sale/HR chạy A2A server cục bộ
python ../../scripts/local_stack.py --feedback "yêu cầu sửa: giảm ngân sách 20%||duyệt"
.venv/bin/crewai deploy validate
```
