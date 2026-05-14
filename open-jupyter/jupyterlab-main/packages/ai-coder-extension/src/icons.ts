// Copyright (c) Jupyter Studio AI.

import { LabIcon } from '@jupyterlab/ui-components';

// A minimal sparkle icon (✨) used as the AI motif. Single colour, themed via
// currentColor so the LabIcon machinery can recolour for dark mode.
const aiCoderSparkleSvgstr = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v6"/><path d="M12 16v6"/><path d="M2 12h6"/><path d="M16 12h6"/><path d="M5 5l3 3"/><path d="M16 16l3 3"/><path d="M19 5l-3 3"/><path d="M8 16l-3 3"/></svg>`;

export const aiCoderSparkleIcon = new LabIcon({
  name: 'ai-coder:sparkle',
  svgstr: aiCoderSparkleSvgstr
});

const aiCoderRobotSvgstr = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V4h8v3"/><circle cx="9" cy="13" r="1"/><circle cx="15" cy="13" r="1"/><path d="M9 17h6"/></svg>`;

export const aiCoderRobotIcon = new LabIcon({
  name: 'ai-coder:robot',
  svgstr: aiCoderRobotSvgstr
});
