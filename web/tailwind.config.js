/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        pitch: '#2d5a27',
        dark: '#0a0e1a',
        'dark-card': '#0f1629',
        'dark-border': '#1e293b',
        accent: '#4fc3f7',
        gold: '#d4a843',
        'gold-light': '#f0d078',
        danger: '#ef5350',
      },
    },
  },
  plugins: [],
}
