// Thin-stroke icons, used sparingly (mobile tab bar, check marks).
const paths = {
  home: <path d="M4 10.5 12 4l8 6.5V20h-5v-5.5H9V20H4z" />,
  history: (
    <>
      <path d="M3.5 12a8.5 8.5 0 1 0 2.5-6L3.5 8.5" />
      <path d="M3.5 4v4.5H8" />
      <path d="M12 7.5V12l3 2" />
    </>
  ),
  trend: (
    <>
      <path d="M3.5 19.5h17" />
      <path d="m4.5 15 4.5-4.5 3.5 3 7-7" />
      <path d="M15.5 6.5h4v4" />
    </>
  ),
  phone: (
    <>
      <rect x="7" y="3" width="10" height="18" rx="2.2" />
      <path d="M11 17.5h2" />
    </>
  ),
  check: <path d="m5.5 12.5 4 4 9-9" />,
};

export type IconName = keyof typeof paths;

export function Icon({ name }: { name: IconName }) {
  return (
    <svg className="icon" viewBox="0 0 24 24" aria-hidden="true">
      {paths[name]}
    </svg>
  );
}
