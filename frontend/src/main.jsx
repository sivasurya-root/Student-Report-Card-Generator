import React, { useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import {
  AlertCircle, BookOpen, CheckCircle2, ChevronRight, Download, FileSpreadsheet,
  GraduationCap, Search, ShieldCheck, UploadCloud, Users, RefreshCw
} from 'lucide-react'
import './index.css'

const API = 'http://127.0.0.1:8000/api'

const gradeLegend = [
  ['O', '91–100', '10'], ['A+', '81–90', '9'], ['A', '71–80', '8'],
  ['B+', '61–70', '7'], ['B', '51–60', '6'], ['C', '45–50', '5'], ['U / RA', '<45', '0'],
]

function App() {
  const [file, setFile] = useState(null)
  const [status, setStatus] = useState('No dataset loaded')
  const [uploading, setUploading] = useState(false)
  const [query, setQuery] = useState('')
  const [students, setStudents] = useState([])
  const [selected, setSelected] = useState(null)
  const [report, setReport] = useState(null)
  const [error, setError] = useState('')
  const [searching, setSearching] = useState(false)

  const loadStudents = async (q = '') => {
    setSearching(true)
    try {
      const r = await fetch(`${API}/students?query=${encodeURIComponent(q)}`)
      if (!r.ok) throw new Error('Could not load students')
      setStudents(await r.json())
    } catch (e) { setError(e.message) }
    finally { setSearching(false) }
  }

  useEffect(() => {
    const timer = setTimeout(() => loadStudents(query), 180)
    return () => clearTimeout(timer)
  }, [query])

  const upload = async () => {
    if (!file) return
    setUploading(true); setError('')
    try {
      const fd = new FormData(); fd.append('file', file)
      const r = await fetch(`${API}/upload`, { method: 'POST', body: fd })
      const data = await r.json()
      if (!r.ok) throw new Error(data.detail || 'Upload failed')
      setStatus(`${data.students} students • ${data.subjects} subjects`)
      setQuery('')
      await loadStudents('')
      setSelected(null); setReport(null)
    } catch (e) { setError(e.message) }
    finally { setUploading(false) }
  }

  const selectStudent = async (student) => {
    setSelected(student); setError('')
    try {
      const r = await fetch(`${API}/students/${encodeURIComponent(student.register_no)}`)
      const data = await r.json()
      if (!r.ok) throw new Error(data.detail || 'Could not load report')
      setReport(data)
    } catch (e) { setError(e.message); setReport(null) }
  }

  const download = async () => {
    if (!selected) return
    const r = await fetch(`${API}/report/${encodeURIComponent(selected.register_no)}`)
    if (!r.ok) { setError('Could not generate PDF'); return }
    const blob = await r.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a'); a.href = url
    a.download = `${selected.student_name.replace(/\s+/g, '_')}_CAT1_Report.pdf`
    a.click(); URL.revokeObjectURL(url)
  }

  const stats = useMemo(() => report?.summary, [report])

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-wrap">
          <div className="brand-mark"><GraduationCap size={25}/></div>
          <div>
            <div className="college-name">SARDAR RAJA COLLEGE OF ENGINEERING</div>
            <div className="college-address">Raja Nagar, Alangulam, Tenkasi</div>
            <div className="dept-line">B.Tech (Artificial Intelligence & Data Science)</div>
          </div>
        </div>
        <div className="utility-tag"><ShieldCheck size={15}/> Academic Report System</div>
      </header>

      <main className="page">
        <section className="hero">
          <div>
            <div className="eyebrow">ACADEMIC ASSESSMENT</div>
            <h1>Student Report Card Generator</h1>
            <p>Upload the official Excel dataset, select a student, and generate a clean A4-ready CAT-1 report.</p>
          </div>
          <div className="exam-chip"><BookOpen size={16}/><span>Continuous Assessment Test – I</span></div>
        </section>

        <section className="stats-row">
          <div className="metric"><Users size={19}/><div><b>{students.length || '—'}</b><span>Students visible</span></div></div>
          <div className="metric"><FileSpreadsheet size={19}/><div><b>{status}</b><span>Dataset status</span></div></div>
          <div className="metric"><ShieldCheck size={19}/><div><b>45%</b><span>Minimum pass mark</span></div></div>
        </section>

        <section className="workspace">
          <div className="left-stack">
            <div className="card upload-card">
              <div className="section-heading"><div><h2>1. Load Dataset</h2><p>Use your final Student_Data + Subject_Config Excel workbook.</p></div><FileSpreadsheet size={22}/></div>
              <label className="dropzone">
                <input type="file" accept=".xlsx,.xls" onChange={e => setFile(e.target.files?.[0] || null)} />
                <UploadCloud size={28}/>
                <strong>{file ? file.name : 'Choose Excel workbook'}</strong>
                <span>{file ? 'Ready to upload' : 'XLSX or XLS • final master template'}</span>
              </label>
              <button className="primary-btn full" disabled={!file || uploading} onClick={upload}>
                {uploading ? <RefreshCw size={18} className="spin"/> : <UploadCloud size={18}/>} {uploading ? 'Loading Dataset…' : 'Upload Final Dataset'}
              </button>
            </div>

            <div className="card student-card">
              <div className="section-heading"><div><h2>2. Select Student</h2><p>Search by name or register number.</p></div><Search size={22}/></div>
              <div className="searchbox"><Search size={18}/><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search student…" />{searching && <RefreshCw size={15} className="spin muted"/>}</div>
              <div className="student-list">
                {students.length === 0 && <div className="empty"><Users size={25}/><b>{status === 'No dataset loaded' ? 'Upload a dataset to begin' : 'No matching student'}</b><span>Student records will appear here.</span></div>}
                {students.map(s => (
                  <button key={s.register_no} className={`student-row ${selected?.register_no === s.register_no ? 'active' : ''}`} onClick={() => selectStudent(s)}>
                    <div><strong>{s.student_name}</strong><span>{s.register_no}</span></div><ChevronRight size={16}/>
                  </button>
                ))}
              </div>
            </div>

            <div className="card grade-card">
              <div className="section-heading"><div><h2>Grading Scale</h2><p>Configured for your CAT-1 workflow.</p></div></div>
              <div className="grade-grid">{gradeLegend.map(([g, range, gp]) => <div key={g}><b>{g}</b><span>{range}</span><em>{gp}</em></div>)}</div>
            </div>
          </div>

          <div className="card report-card">
            <div className="report-toolbar"><div><h2>3. Report Preview</h2><p>Professional academic report generated from the selected record.</p></div><button className="secondary-btn" disabled={!report} onClick={download}><Download size={17}/> Download PDF</button></div>
            {error && <div className="error"><AlertCircle size={17}/>{error}</div>}
            {!report ? (
              <div className="report-empty"><div className="paper-icon"><FileSpreadsheet size={29}/></div><h3>Select a student</h3><p>The full report card preview will appear here after you select a record.</p></div>
            ) : (
              <div className="paper">
                <div className="paper-head"><div className="crest"><GraduationCap size={27}/></div><div><div className="paper-college">SARDAR RAJA COLLEGE OF ENGINEERING</div><div className="paper-sub">Raja Nagar, Alangulam, Tenkasi</div><div className="paper-dept">B.Tech (Artificial Intelligence & Data Science)</div></div></div>
                <div className="paper-title">CONTINUOUS ASSESSMENT TEST – I EXAMINATION</div>
                <div className="paper-meta"><span>Report ID: <b>{report.meta.report_id}</b></span><span>Academic Year: <b>{report.student['Academic Year'] || '—'}</b></span></div>

                <div className="detail-grid">
                  {[['Student Name', report.student['Student Name']],['Register No', report.student['Register Number']],['Department', report.meta.department],['Programme', report.meta.programme],['Semester', report.student.Semester],['Section', report.student.Section],['Attendance', report.meta.attendance || '—'],['DOB', report.student['Date of Birth'] || '—'],['Academic Year', report.student['Academic Year'] || '—']].map(([k,v]) => <div key={k}><span>{k}</span><b>{v || '—'}</b></div>)}
                </div>

                <div className="paper-section-title">ACADEMIC PERFORMANCE</div>
                <div className="table-wrap"><table><thead><tr><th>COURSE CODE</th><th>COURSE / SUBJECT</th><th>MAX</th><th>MARK</th><th>%</th><th>GRADE</th><th>GP</th><th>STATUS</th></tr></thead><tbody>
                  {report.subjects.map(s => <tr key={`${s.code}-${s.name}`}><td>{s.code}</td><td className="subject">{s.name}</td><td>{s.max_mark}</td><td className="bold">{s.mark}</td><td>{s.percentage}</td><td className="bold">{s.grade}</td><td>{s.grade_point}</td><td>{s.status}</td></tr>)}
                </tbody></table></div>

                <div className="summary-grid">
                  {[['Total Marks', `${stats.total_marks} / ${stats.max_marks}`],['Percentage', `${stats.percentage}%`],['Overall Grade', stats.overall_grade],['Avg. Grade Point', stats.average_grade_point]].map(([k,v]) => <div key={k}><span>{k}</span><b>{v}</b></div>)}
                </div>
                <div className={`result-band ${stats.result.startsWith('PASS') ? 'pass' : 'fail'}`}><span>FINAL RESULT</span><b>{stats.result}</b><small>{stats.arrear_count} arrear(s)</small></div>
                <div className="signature-row"><div>Class Advisor</div><div>Head of Department</div><div>Principal</div></div>
                <div className="paper-foot">Computer-generated academic report • Verification ID {report.meta.report_id}</div>
              </div>
            )}
          </div>
        </section>
      </main>
    </div>
  )
}

createRoot(document.getElementById('root')).render(<App />)
