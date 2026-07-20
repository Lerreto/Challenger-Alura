import type { SVGProps } from 'react'

type IconProps = SVGProps<SVGSVGElement>

function Icon({ children, ...props }: IconProps) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    >
      {children}
    </svg>
  )
}

export const SparkIcon = (props: IconProps) => (
  <Icon {...props}><path d="m12 2-1.4 5.1a5 5 0 0 1-3.5 3.5L2 12l5.1 1.4a5 5 0 0 1 3.5 3.5L12 22l1.4-5.1a5 5 0 0 1 3.5-3.5L22 12l-5.1-1.4a5 5 0 0 1-3.5-3.5Z" /></Icon>
)
export const FilesIcon = (props: IconProps) => (
  <Icon {...props}><path d="M15 2H6a2 2 0 0 0-2 2v13" /><path d="M8 6h10a2 2 0 0 1 2 2v12H8a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2Z" /><path d="M10 11h6M10 15h5" /></Icon>
)
export const UploadIcon = (props: IconProps) => (
  <Icon {...props}><path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5" /><path d="M5 14v5a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-5" /></Icon>
)
export const RefreshIcon = (props: IconProps) => (
  <Icon {...props}><path d="M20 7h-5V2" /><path d="M20 7a8 8 0 1 0 1 8" /></Icon>
)
export const TrashIcon = (props: IconProps) => (
  <Icon {...props}><path d="M4 7h16M9 7V4h6v3m3 0-1 14H7L6 7m4 4v6m4-6v6" /></Icon>
)
export const SendIcon = (props: IconProps) => (
  <Icon {...props}><path d="m22 2-7 20-4-9-9-4Z" /><path d="M22 2 11 13" /></Icon>
)
export const MenuIcon = (props: IconProps) => (
  <Icon {...props}><path d="M4 7h16M4 12h16M4 17h16" /></Icon>
)
export const CloseIcon = (props: IconProps) => (
  <Icon {...props}><path d="m6 6 12 12M18 6 6 18" /></Icon>
)
export const ShieldIcon = (props: IconProps) => (
  <Icon {...props}><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z" /><path d="m9 12 2 2 4-4" /></Icon>
)
export const DocumentIcon = (props: IconProps) => (
  <Icon {...props}><path d="M6 2h8l4 4v16H6Z" /><path d="M14 2v5h5M9 12h6M9 16h6" /></Icon>
)
export const ChevronIcon = (props: IconProps) => (
  <Icon {...props}><path d="m9 18 6-6-6-6" /></Icon>
)
export const WarningIcon = (props: IconProps) => (
  <Icon {...props}><path d="M10.3 3.7 2.6 17a2 2 0 0 0 1.7 3h15.4a2 2 0 0 0 1.7-3L13.7 3.7a2 2 0 0 0-3.4 0Z" /><path d="M12 9v4m0 3h.01" /></Icon>
)
export const ThumbsUpIcon = (props: IconProps) => (
  <Icon {...props}><path d="M7 22V11m0 11H4a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1h3m0 11 4.4 1.47a3 3 0 0 0 .95.16h6.13a2 2 0 0 0 2-1.68l1.13-6.78A2 2 0 0 0 19.61 11H14V6a2 2 0 0 0-2-2h-.34a1 1 0 0 0-.95.68L9 11" /></Icon>
)
export const ThumbsDownIcon = (props: IconProps) => (
  <Icon {...props}><path d="M17 2v11m0 11h3a1 1 0 0 0 1-1v-9a1 1 0 0 0-1-1h-3m0-11-4.4-1.47a3 3 0 0 0-.95-.16H5.5a2 2 0 0 0-2 1.68L2.37 8.85A2 2 0 0 0 4.39 11H10v5a2 2 0 0 0 2 2h.34a1 1 0 0 0 .95-.68L15 11" /></Icon>
)
