# Job Search Web UI

A modern web interface for managing your job search automation data.

## Features

- 📊 **Stats Dashboard** - Visual pipeline statistics with clickable filters
- 🔍 **Search & Filter** - Search by title, company, or location
- 🏷️ **Status Management** - Dropdown to update job statuses
- 📱 **Responsive Design** - Works on desktop and mobile
- ⚡ **Fast & Modern** - Built with Vite + React + TypeScript

## Getting Started

### 1. Install Dependencies

```bash
cd web
npm install
```

### 2. Start the API Server (in another terminal)

```bash
cd ~/job-search-automation
source venv/bin/activate
python api_server.py
```

### 3. Start the Web UI

```bash
cd web
npm run dev
```

Open http://localhost:5173 in your browser.

## API Endpoints

The web UI expects a REST API at `http://localhost:8000`:

- `GET /api/jobs` - Get all jobs (optionally filter by `?status=`)
- `GET /api/stats` - Get pipeline statistics
- `PUT /api/jobs/{id}/status` - Update job status

## Project Structure

```
web/
├── src/
│   ├── components/
│   │   ├── ui/           # shadcn/ui components
│   │   ├── JobList.tsx   # Main job list
│   │   ├── JobCard.tsx   # Individual job card
│   │   ├── StatusDropdown.tsx
│   │   ├── StatsPanel.tsx
│   │   └── SearchFilter.tsx
│   ├── hooks/
│   │   └── useJobs.ts    # Data fetching hook
│   ├── types/
│   │   └── job.ts        # TypeScript types
│   ├── lib/
│   │   └── utils.ts      # Utility functions
│   ├── App.tsx
│   ├── main.tsx
│   └── index.css
├── package.json
├── vite.config.ts
└── README.md
```

## Customization

The UI uses Tailwind CSS for styling. You can customize colors in:
- `tailwind.config.js` - Theme configuration
- `src/index.css` - CSS variables for light/dark mode

## Production Build

```bash
npm run build
```

Output goes to `dist/` folder.