# ER Diagram

```mermaid
erDiagram
    USERS ||--o{ SESSIONS : "has"
    USERS ||--o{ RESUMES : "uploads"
    USERS ||--o{ JOBS : "creates"
    USERS ||--o{ CHAT_HISTORY : "asks"
    RESUMES ||--o| ANALYSES : "has one"
    RESUMES ||--o{ RECOMMENDATIONS : "receives"
    JOBS ||--o{ RECOMMENDATIONS : "recommended in"

    USERS { int id PK
            text name
            text email UK
            text password_hash
            text salt
            text created_at }
    SESSIONS { text token PK
               int user_id FK
               text created_at }
    RESUMES { int id PK
              int user_id FK
              text filename
              text raw_text
              text uploaded_at }
    ANALYSES { int id PK
               int resume_id FK "UNIQUE"
               text contact_json
               text technical_skills_json
               text soft_skills_json
               text education_json
               text experience_json
               text summary }
    JOBS { int id PK
           text title
           text company
           text location
           text job_type
           text description
           text required_skills_json
           int created_by FK }
    RECOMMENDATIONS { int id PK
                      int resume_id FK
                      int job_id FK
                      real score
                      text explanation }
    CHAT_HISTORY { int id PK
                   int user_id FK
                   text question
                   text answer }
```

The knowledge base (skills, roadmaps, guidelines, learning resources) lives in `data/*.json` and is indexed in memory by the RAG retriever; job descriptions in the `jobs` table are added to the index at query time.
