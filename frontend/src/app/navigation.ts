import {
  ArrowLeftRight,
  BarChart3,
  Building2,
  HelpCircle,
  LayoutDashboard,
  Map,
  Settings,
  Shuffle,
  Star,
  TrendingUp,
  Upload,
  UserCog,
  Users,
  type LucideIcon,
} from 'lucide-react';
import { pickLabel } from '../shared/i18n/language';
import type { BilingualLabel, Language } from '../shared/i18n/types';

export const routes = Object.freeze({
  root: '/',
  login: '/login',
  dashboard: '/dashboard',
  systemOverview: '/system-overview',
  students: '/students',
  uploads: '/upload',
  assistedAllocation: '/assisted-allocation',
  priority: '/priority',
  allocation: '/allocation',
  allocationResults: '/allocation/results',
  transfers: '/transfers',
  inventory: '/buildings',
  map: '/map',
  reports: '/reports',
  analytics: '/analysis',
  staff: '/users',
  whatIf: '/what-if',
  settings: '/settings',
});

export type RouteId = keyof typeof routes;

/** A quick-search destination: its bilingual label plus the terms it matches. */
export interface SearchEntry extends BilingualLabel {
  keywords: string[];
}

/** The capability helpers AuthContext exposes that may gate a sidebar entry. */
export type SidebarCapability = 'canUploadExcel' | 'canAssistAllocation' | 'canManageUsers';

export interface SidebarEntry extends BilingualLabel {
  icon: LucideIcon;
  capability: SidebarCapability | null;
}

interface NavigationEntry {
  search?: SearchEntry;
  sidebar?: SidebarEntry;
}

// Search and sidebar presentation intentionally differ; destinations have one owner.
const navigation: Partial<Record<RouteId, NavigationEntry>> = {
  root: {
    search: {
        labelHe: 'דף הבית',
        labelEn: 'Home',
        keywords: [
          'בית',
          'דף הבית',
          'ראשי',
          'dashboard',
          'home',
        ],
      },
  },
  students: {
    search: {
        labelHe: 'סטודנטים',
        labelEn: 'Students',
        keywords: [
          'סטודנט',
          'סטודנטים',
          'students',
          'student',
        ],
      },
    sidebar: { icon: Users, labelHe: 'סטודנטים', labelEn: 'Students', capability: null },
  },
  allocation: {
    search: {
        labelHe: 'שיבוץ',
        labelEn: 'Allocation',
        keywords: [
          'שיבוץ',
          'הקצאה',
          'allocation',
        ],
      },
    sidebar: { icon: Shuffle, labelHe: 'שיבוץ', labelEn: 'Allocation', capability: null },
  },
  allocationResults: {
    search: {
        labelHe: 'תוצאות שיבוץ',
        labelEn: 'Allocation Results',
        keywords: [
          'תוצאות',
          'תוצאות שיבוץ',
          'שיבוץ תוצאות',
          'allocation results',
          'results',
        ],
      },
  },
  transfers: {
    search: {
        labelHe: 'בקשות מעבר',
        labelEn: 'Transfer Requests',
        keywords: [
          'בקשות',
          'בקשה',
          'בקשות מעבר',
          'בקשת מעבר',
          'מעבר',
          'transfer',
          'requests',
        ],
      },
    sidebar: { icon: ArrowLeftRight, labelHe: 'בקשות מעבר', labelEn: 'Transfer Requests', capability: null },
  },
  inventory: {
    search: {
        labelHe: 'בניינים וחדרים',
        labelEn: 'Buildings and Rooms',
        keywords: [
          'בניין',
          'בניינים',
          'חדר',
          'חדרים',
          'דירה',
          'דירות',
          'בניינים וחדרים',
          'buildings',
          'rooms',
          'apartments',
        ],
      },
    sidebar: { icon: Building2, labelHe: 'בניינים וחדרים', labelEn: 'Buildings and Rooms', capability: null },
  },
  map: {
    search: {
        labelHe: 'מפת המעונות',
        labelEn: 'Dormitory Map',
        keywords: [
          'מפה',
          'מפת המעונות',
          'מפת מעונות',
          'מעונות',
          'map',
          'dormitory map',
        ],
      },
    sidebar: { icon: Map, labelHe: 'מפת המעונות', labelEn: 'Dormitory Map', capability: null },
  },
  reports: {
    search: {
        labelHe: 'דוחות',
        labelEn: 'Reports',
        keywords: [
          'דוח',
          'דוחות',
          'reports',
          'report',
        ],
      },
    sidebar: { icon: BarChart3, labelHe: 'דוחות', labelEn: 'Reports', capability: null },
  },
  analytics: {
    search: {
        labelHe: 'ניתוח נתונים',
        labelEn: 'Data Analysis',
        keywords: [
          'ניתוח',
          'ניתוח נתונים',
          'נתונים',
          'סטטיסטיקה',
          'אנליזה',
          'analysis',
          'analytics',
          'data analysis',
        ],
      },
    sidebar: { icon: TrendingUp, labelHe: 'ניתוח נתונים', labelEn: 'Data Analysis', capability: null },
  },
  staff: {
    search: {
        labelHe: 'מידע על עובדים',
        labelEn: 'Staff Information',
        keywords: [
          'עובד',
          'עובדים',
          'מידע על עובדים',
          'צוות',
          'מנהלים',
          'staff',
          'employees',
        ],
      },
    sidebar: { icon: UserCog, labelHe: 'מידע על עובדים', labelEn: 'Employee Information', capability: 'canManageUsers' },
  },
  whatIf: {
    search: {
        labelHe: 'כללי מה אם',
        labelEn: 'What If Rules',
        keywords: [
          'מה אם',
          'כללי מה אם',
          'what if',
          'what-if',
          'rules',
        ],
      },
    sidebar: { icon: HelpCircle, labelHe: 'כללי מה אם', labelEn: 'What-If Rules', capability: null },
  },
  settings: {
    search: {
        labelHe: 'הגדרות',
        labelEn: 'Settings',
        keywords: [
          'הגדרות',
          'הגדרה',
          'settings',
          'preferences',
        ],
      },
    sidebar: { icon: Settings, labelHe: 'הגדרות', labelEn: 'Settings', capability: null },
  },
  dashboard: {
    sidebar: { icon: LayoutDashboard, labelHe: 'דף הבית', labelEn: 'Home', capability: null },
  },
  uploads: {
    sidebar: { icon: Upload, labelHe: 'העלאת קובץ', labelEn: 'Upload File', capability: 'canUploadExcel' },
  },
  assistedAllocation: {
    sidebar: { icon: Star, labelHe: 'שיבוץ ידני', labelEn: 'Manual Allocation', capability: 'canAssistAllocation' },
  },
};

interface SidebarGroupDefinition extends BilingualLabel {
  key: string;
  items: RouteId[];
}

const groups: SidebarGroupDefinition[] = [
  { key: 'main', labelHe: 'ראשי', labelEn: 'Main', items: ['dashboard'] },
  { key: 'students', labelHe: 'ניהול סטודנטים', labelEn: 'Student Management', items: ['uploads', 'students', 'assistedAllocation'] },
  { key: 'allocation', labelHe: 'תהליך השיבוץ', labelEn: 'Allocation Process', items: ['allocation', 'transfers'] },
  { key: 'dormitory', labelHe: 'ניהול מעונות', labelEn: 'Dormitory Management', items: ['inventory', 'map'] },
  { key: 'reports', labelHe: 'דוחות ונתונים', labelEn: 'Reports and Data', items: ['reports', 'analytics'] },
  { key: 'system', labelHe: 'ניהול מערכת', labelEn: 'System Management', items: ['staff', 'whatIf', 'settings'] },
];

export interface HeaderNavigationItem extends SearchEntry {
  path: string;
}

const isRouteId = (id: string): id is RouteId => id in routes;

export const headerNavigation: HeaderNavigationItem[] = Object.entries(navigation)
  .filter(([id, item]) => isRouteId(id) && item?.search)
  .map(([id, item]) => ({ ...(item as Required<Pick<NavigationEntry, 'search'>>).search, path: routes[id as RouteId] }));

export interface SidebarItem {
  path: string;
  icon: LucideIcon;
  label: string;
  show: boolean;
}

export interface SidebarGroup {
  key: string;
  title: string;
  items: SidebarItem[];
}

export type SidebarCapabilities = Record<SidebarCapability, () => boolean>;

export function getSidebarGroups(language: Language, capabilities: SidebarCapabilities): SidebarGroup[] {
  return groups.map(({ key, labelHe, labelEn, items }) => ({
    key,
    title: pickLabel({ labelHe, labelEn }, language),
    items: items.map((id) => {
      const item = navigation[id]?.sidebar;
      if (!item) {
        throw new Error(`Navigation entry "${id}" has no sidebar presentation`);
      }
      return {
        path: routes[id],
        icon: item.icon,
        label: pickLabel(item, language),
        show: item.capability ? capabilities[item.capability]() : true,
      };
    }),
  }));
}
