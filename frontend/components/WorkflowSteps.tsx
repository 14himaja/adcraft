import React from 'react';

interface WorkflowStepsProps {
  onStepClick?: (stepNumber: number) => void;
}

const STEPS = ['Your idea', 'AI drafts the ad', 'Review and edit', 'Publish'];

export function WorkflowSteps({ onStepClick }: WorkflowStepsProps) {
  return (
    <ol className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-[#7A6C63] dark:text-slate-400 border-b border-[#EDE6DD] dark:border-white/10 pb-4">
      {STEPS.map((title, i) => (
        <li key={title}>
          <button type="button" onClick={() => onStepClick?.(i + 1)} className="hover:text-[#F26D5B] cursor-pointer">
            <span className="font-bold text-[#1F1A18] dark:text-white">{i + 1}.</span> {title}
          </button>
        </li>
      ))}
    </ol>
  );
}
