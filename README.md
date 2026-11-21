# Conversational Intelligence Studio

**Understand the conversations behind your business.**

Conversational Intelligence Studio (CIS) is a multi-analyst conversational intelligence application designed to help users extract meaningful insights from customer and workplace conversations.

The platform provides specialised analysis modes for examining conversational intent, recurring concerns, unresolved follow-ups, communication patterns and potential operational blockers.

## Overview

CIS brings three specialised analytical perspectives into a unified workspace:

### Customer Intelligence
Analyse customer-facing conversations to identify intent, recurring complaints, service friction, unresolved queries and follow-up opportunities.

### Workplace Intelligence
Examine internal team conversations to surface blockers, unanswered questions, recurring issues and topics that may require human attention.

### Communication Patterns
Explore group communication dynamics, including who raises topics, who responds, how information is handed off and where conversations tend to stall.

Each analyst operates through a dedicated workspace with its own conversation history and analysis context.

## Key Features

- **Specialised analyst workspaces:** Three dedicated modes for customer, workplace and communication analysis.
- **Conversational interface:** Submit conversation text and ask contextual follow-up questions.
- **Session management:** Create, revisit and manage separate conversations.
- **Evidence-oriented analysis:** Encourage findings grounded in supplied conversational evidence and direct quotations.
- **Response metadata:** Surface technical information associated with generated responses.
- **Personalisation and accessibility:** Light, dark and system themes, text scaling, contrast and motion preferences.
- **Persistent preferences:** Retain interface and analysis preferences across sessions.

## Technology Stack

| Layer | Technology |
|---|---|
| Frontend | React |
| Build tooling | Vite |
| Backend | Python, FastAPI |
| LLM integration | LiteLLM |
| Database | SQLite |
| Containerisation | Docker, Docker Compose |

## Architecture

CIS uses a frontend-backend architecture.

The React frontend provides the user interface, analyst workspaces, conversation management and accessibility preferences.

The FastAPI backend manages conversation processing, session persistence, LLM requests, response caching and provider failover.

LiteLLM provides the unified interface for language model integration, while SQLite stores conversation history and associated response metadata.

## Project Structure

```text
conversational-intelligence-studio/
│
├── cis-frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── data/
│   │   └── services/
│   ├── package.json
│   └── vite.config.js
│
├── backend/
│
├── docker-compose.yml
├── Makefile
├── .env.example
├── .gitignore
└── README.md
```

## Getting Started

### Prerequisites

- Node.js and npm
- Python
- Docker and Docker Compose
- API credentials for a supported language model provider

### Frontend Setup

```bash
cd cis-frontend
npm install
npm run dev
```

### Backend Setup

Backend setup instructions and environment configuration will be documented alongside the backend implementation.

### Running with Docker

The complete application is intended to run through:

```bash
make up
```

To stop the application:

```bash
make down
```

## Configuration

Application credentials and environment-specific settings should be supplied through environment variables.

Use the provided `.env.example` as a reference when configuring a local environment.

Never commit API keys, credentials or private environment files.

## Responsible Use

CIS is intended to support human understanding of conversations, not replace human judgement.

Its analytical outputs should be interpreted in context and verified against the underlying conversation. The platform should not be used to infer sensitive personal attributes, make unsupported claims about individuals, or automate employment, disciplinary or other consequential decisions.

Users should obtain appropriate permission and anonymise personal information before submitting conversation data.

## License

To be determined.