import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
// Tailwind utilities first, then our globals so the `.ps-*` identity always wins.
import './preview-tailwind.css';
import './globals.css';
import { Preview } from './preview';

const root = document.getElementById('root');
if (!root) throw new Error('Preview root element #root not found');

createRoot(root).render(
  <StrictMode>
    <Preview />
  </StrictMode>,
);
