'use client';

import { useSettings } from '@/contexts/SettingsContext';

export default function ThemeToggle() {
  const { settings, toggleTheme } = useSettings();
  const isDark = settings.theme === 'dark';

  return (
    <button
      onClick={toggleTheme}
      className="relative w-14 h-7 rounded-full transition-all duration-300 focus:outline-none focus:ring-2 focus:ring-accent/50"
      style={{
        background: isDark 
          ? 'linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)' 
          : 'linear-gradient(135deg, #87CEEB 0%, #f0f8ff 100%)',
        border: `1px solid ${isDark ? '#333' : '#ccc'}`,
      }}
      aria-label={isDark ? 'Переключить на светлую тему' : 'Переключить на тёмную тему'}
    >
      {/* Sun icon */}
      <span
        className={`absolute left-1 top-1/2 -translate-y-1/2 w-5 h-5 flex items-center justify-center transition-all duration-300 ${
          isDark ? 'opacity-30 scale-75' : 'opacity-100 scale-100'
        }`}
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="#FFD700"
          className="w-4 h-4"
        >
          <path d="M12 2.25a.75.75 0 01.75.75v2.25a.75.75 0 01-1.5 0V3a.75.75 0 01.75-.75zM7.5 12a4.5 4.5 0 119 0 4.5 4.5 0 01-9 0zM18.894 6.166a.75.75 0 00-1.06-1.06l-1.591 1.59a.75.75 0 101.06 1.061l1.591-1.59zM21.75 12a.75.75 0 01-.75.75h-2.25a.75.75 0 010-1.5H21a.75.75 0 01.75.75zM17.834 18.894a.75.75 0 001.06-1.06l-1.59-1.591a.75.75 0 10-1.061 1.06l1.59 1.591zM12 18a.75.75 0 01.75.75V21a.75.75 0 01-1.5 0v-2.25A.75.75 0 0112 18zM7.758 17.303a.75.75 0 00-1.061-1.06l-1.591 1.59a.75.75 0 001.06 1.061l1.591-1.59zM6 12a.75.75 0 01-.75.75H3a.75.75 0 010-1.5h2.25A.75.75 0 016 12zM6.697 7.757a.75.75 0 001.06-1.06l-1.59-1.591a.75.75 0 00-1.061 1.06l1.59 1.591z" />
        </svg>
      </span>

      {/* Moon icon */}
      <span
        className={`absolute right-1 top-1/2 -translate-y-1/2 w-5 h-5 flex items-center justify-center transition-all duration-300 ${
          isDark ? 'opacity-100 scale-100' : 'opacity-30 scale-75'
        }`}
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="#E8E8E8"
          className="w-4 h-4"
        >
          <path
            fillRule="evenodd"
            d="M9.528 1.718a.75.75 0 01.162.819A8.97 8.97 0 009 6a9 9 0 009 9 8.97 8.97 0 003.463-.69.75.75 0 01.981.98 10.503 10.503 0 01-9.694 6.46c-5.799 0-10.5-4.701-10.5-10.5 0-4.368 2.667-8.112 6.46-9.694a.75.75 0 01.818.162z"
            clipRule="evenodd"
          />
        </svg>
      </span>

      {/* Toggle circle */}
      <span
        className={`absolute top-1 w-5 h-5 rounded-full shadow-md transition-all duration-300 ${
          isDark ? 'left-7' : 'left-1'
        }`}
        style={{
          background: isDark 
            ? 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)' 
            : 'linear-gradient(135deg, #FFD700 0%, #FFA500 100%)',
          boxShadow: isDark 
            ? '0 2px 8px rgba(102, 126, 234, 0.5)' 
            : '0 2px 8px rgba(255, 215, 0, 0.5)',
        }}
      />
    </button>
  );
}
