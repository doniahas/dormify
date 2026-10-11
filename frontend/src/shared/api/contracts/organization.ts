// backend/api/serializers/organization.py

/** RegionSerializer. Region.id is a slug-like string primary key. */
export interface Region {
  id: string;
  name: string;
}

/** DormTypeSerializer. `code` is the official numeric dorm-type code. */
export interface DormType {
  id: number;
  /** DormType.code is nullable. */
  code: number | null;
  name: string;
  region: string;
  region_name: string;
}
