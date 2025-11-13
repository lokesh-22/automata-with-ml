"use client";
import React, { useEffect, useRef } from 'react';

type Props = { dot: string };

export default function RegexVisualizer({ dot }: Props) {
  const ref = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        // Dynamically import viz and its renderer to keep this import client-only and avoid
        // Turbopack trying to resolve it during server build.
        const VizModule: any = await import('viz.js');
        const Full: any = await import('viz.js/full.render.js');
        const Viz = VizModule.default || VizModule;
        const viz = new Viz({ Module: Full.Module, render: Full.render });
        const element: SVGElement = await viz.renderSVGElement(dot);
        if (!mounted) return;
        if (ref.current) {
          ref.current.innerHTML = '';
          ref.current.appendChild(element);
        }
      } catch (err: any) {
        console.error('Viz render error', err);
        if (ref.current) ref.current.innerText = 'Error rendering graph: ' + String(err);
      }
    })();
    return () => {
      mounted = false;
    };
  }, [dot]);
  return <div ref={ref} />;
}
