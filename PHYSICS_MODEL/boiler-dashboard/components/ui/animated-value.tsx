import { useState, useEffect, useRef } from "react";

export function AnimatedValue({ value }: { value: string | number }) {
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (ref.current) {
      ref.current.classList.remove('animate-number-pop');
      void ref.current.offsetWidth; // reflow
      ref.current.classList.add('animate-number-pop');
    }
  }, [value]);
  return <span ref={ref} className="animate-number-pop">{value}</span>;
}
