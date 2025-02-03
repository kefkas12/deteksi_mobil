import math

class Tracker:
    def __init__(self, max_distance=50, timeout=5):
        self.center_points = {}
        self.id_count = 0
        self.max_distance = max_distance
        self.timeout = timeout
        self.lost_objects = {}

    def update(self, objects_rect):
        objects_bbs_ids = []

        for rect in objects_rect:
            x1, y1, x2, y2 = rect
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2

            same_object_detected = False
            for id, pt in self.center_points.items():
                dist = math.hypot(cx - pt[0], cy - pt[1])
                if dist < self.max_distance:
                    self.center_points[id] = (cx, cy)
                    objects_bbs_ids.append([x1, y1, x2, y2, id])
                    same_object_detected = True
                    break

            if not same_object_detected:
                self.center_points[self.id_count] = (cx, cy)
                objects_bbs_ids.append([x1, y1, x2, y2, self.id_count])
                self.id_count += 1

        new_center_points = {}
        for obj_bb_id in objects_bbs_ids:
            _, _, _, _, object_id = obj_bb_id
            center = self.center_points[object_id]
            new_center_points[object_id] = center

        for id, center in self.center_points.items():
            if id not in [obj_bb_id[4] for obj_bb_id in objects_bbs_ids]:
                if id in self.lost_objects:
                    self.lost_objects[id] += 1
                else:
                    self.lost_objects[id] = 1

                if self.lost_objects[id] > self.timeout:
                    del self.lost_objects[id]
            else:
                if id in self.lost_objects:
                    del self.lost_objects[id]

        self.center_points = new_center_points.copy()
        return objects_bbs_ids
