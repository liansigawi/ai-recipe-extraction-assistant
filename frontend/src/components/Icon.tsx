import type { IconName } from '../categoryLook'

// Simple line drawings, 24 x 24, in the text's color. Decorative: the text beside them says the same.
const PATHS: Record<IconName, string> = {
  check: 'M5 12.5l4.2 4.2L19 7',
  circle: 'M12 4.5a7.5 7.5 0 1 0 0 15a7.5 7.5 0 1 0 0-15',
  search: 'M10.5 4a6.5 6.5 0 1 0 0 13a6.5 6.5 0 1 0 0-13M15.5 15.5L20 20',
  plus: 'M12 5v14M5 12h14',
  close: 'M6 6l12 12M18 6L6 18',
  play: 'M8 5.5v13l10.5-6.5z',
  link: 'M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1',
  // Points to the inline start: "back" in a right-to-left page.
  back: 'M5 12h14M13 6l6 6-6 6',
  book: 'M5 4.5h9.5a3 3 0 0 1 3 3V20H8a3 3 0 0 1-3-3zM5 17a3 3 0 0 1 3-3h9.5',
  cake: 'M4 20h16v-7H4zM4 16c2.7 1.3 5.3-1.3 8 0s5.3 1.3 8 0M8 13v-2M12 13V9M16 13v-2M12 9c-1.2-.9-1.2-2.4 0-3.6 1.2 1.2 1.2 2.7 0 3.6',
  pot: 'M3 10h18M5 10v6.5A3.5 3.5 0 0 0 8.5 20h7a3.5 3.5 0 0 0 3.5-3.5V10M9.5 10V8.5a2.5 2.5 0 0 1 5 0V10M8.5 3.5c-.8 1 .8 1.5 0 2.5M12 3c-.8 1 .8 1.5 0 2.5M15.5 3.5c-.8 1 .8 1.5 0 2.5',
  bowl: 'M3 11.5h18a9 9 0 0 1-18 0zM8.5 11.5c-.3-2.7 1.2-4.6 3.5-5.3M12 11.5c.2-3 2.2-5.2 5.5-5.5-.2 3-2.2 5.2-5.5 5.5M9 21h6',
  glass: 'M6.5 6h11l-1.6 14H8.1zM7 10.5h10M13.5 6l2.5-3.5h2.5',
  // A leaf and its vein (salads); a bowl with steam (soups); a bowl of rice with chopsticks (sides); a jar
  // with its lid and label (spreads, dips and sauces); a low bowl heaped with nuts (snacks).
  leaf: 'M5 19C5 10.5 10.5 5 19 5c0 8.5-5.5 14-14 14zM5 19l9-9M9.5 14.5h3M12 12V9',
  soup: 'M3.5 11.5h17a8.5 8.5 0 0 1-17 0zM9 20.5h6M8.5 3.5c-.8 1 .8 2 0 3.5M12 3c-.8 1 .8 2 0 3.5M15.5 3.5c-.8 1 .8 2 0 3.5',
  side: 'M3.5 12.5h17a8.5 7.5 0 0 1-17 0zM6 12.5c.5-2.6 3-4.5 6-4.5s5.5 1.9 6 4.5M9 20.5h6M14 3l-4 7.5M18 3.5l-5.5 6.5',
  jar: 'M7 9h10v9.5A2.5 2.5 0 0 1 14.5 21h-5A2.5 2.5 0 0 1 7 18.5zM6.5 5.5h11V9h-11zM9.5 14h5',
  snack:
    'M3.5 13h17a8.5 7 0 0 1-17 0zM9 20.5h6M6.1 10.6a2.4 2.4 0 1 0 4.8 0a2.4 2.4 0 1 0-4.8 0M13.1 10.6a2.4 2.4 0 1 0 4.8 0a2.4 2.4 0 1 0-4.8 0M9.6 7.2a2.4 2.4 0 1 0 4.8 0a2.4 2.4 0 1 0-4.8 0',
  utensils: 'M7 3v7.5M4.5 3v4.5a2.5 2.5 0 0 0 5 0V3M7 10.5V21M17 3c-2.3 2-2.3 7 0 8.5V21',
}

export default function Icon({ name, className }: { name: IconName; className?: string }) {
  return (
    <svg className={className === undefined ? `icon icon-${name}` : `icon icon-${name} ${className}`} viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d={PATHS[name]} />
    </svg>
  )
}
