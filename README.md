# Student Report Card Generator — Final Excel Template Integration

## Stack
- Frontend: React + Vite + Tailwind CSS
- Backend: FastAPI
- Excel: Pandas + OpenPyXL
- PDF: ReportLab

## Final Excel contract
The application expects the workbook to contain these sheets:
- `Student_Data` — headers on row 4
- `Subject_Config` — headers on row 2
- `Instructions` — informational

`Student_Data` is the master student table. The five marks are read from:
- `Subject 1 Mark` ... `Subject 5 Mark`

The five subject names are read from:
- `Subject 1 Name` ... `Subject 5 Name`

Subject codes and maximum marks are read from `Subject_Config`, ordered by `Report Order`.

## Grading rules
- O: 91–100 → 10
- A+: 81–90 → 9
- A: 71–80 → 8
- B+: 61–70 → 7
- B: 51–60 → 6
- C: 45–50 → 5
- U / RA: below 45 → 0

A student is PASS only when every recorded subject is at least 45%.

## Run backend
```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Backend: http://127.0.0.1:8000/docs

## Run frontend
Open another terminal:
```powershell
cd frontend
npm install
npm run dev
```

Frontend: http://localhost:5173/
