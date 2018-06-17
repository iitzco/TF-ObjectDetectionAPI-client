import numpy as np
import tensorflow as tf
import json
from json import encoder
encoder.FLOAT_REPR = lambda o: format(o, '.2f')

from object_detection.utils import label_map_util
from object_detection.utils import ops as utils_ops
from object_detection.utils import visualization_utils as vis_util

from PIL import Image
import sys

class ObjectDetector(object):

    def __init__(self, graph_path, labels_path, num_classes):
        self.load(graph_path, labels_path, num_classes)


    def load(self, graph_path, labels_path, num_classes):
        detection_graph = tf.Graph()
        with detection_graph.as_default():
            od_graph_def = tf.GraphDef()
            with tf.gfile.GFile(graph_path, 'rb') as fid:
                serialized_graph = fid.read()
                od_graph_def.ParseFromString(serialized_graph)
                tf.import_graph_def(od_graph_def, name='')


        label_map = label_map_util.load_labelmap(labels_path)
        categories = label_map_util.convert_label_map_to_categories(label_map, max_num_classes=num_classes, use_display_name=True)

        self.category_index = label_map_util.create_category_index(categories)
        self.graph = detection_graph
        self.sess = tf.Session(graph=self.graph)


    def _run_inference(self, image):
        with self.graph.as_default():
            ops = tf.get_default_graph().get_operations()

            all_tensor_names = {output.name for op in ops for output in op.outputs}
            tensor_dict = {}
            for key in [
                    'num_detections', 'detection_boxes', 'detection_scores',
                    'detection_classes', 'detection_masks'
            ]:
                tensor_name = key + ':0'
                if tensor_name in all_tensor_names:
                    tensor_dict[key] = tf.get_default_graph().get_tensor_by_name(
                            tensor_name)

            if 'detection_masks' in tensor_dict:
                # The following processing is only for single image
                detection_boxes = tf.squeeze(tensor_dict['detection_boxes'], [0])
                detection_masks = tf.squeeze(tensor_dict['detection_masks'], [0])
                # Reframe is required to translate mask from box coordinates to image coordinates and fit the image size.
                real_num_detection = tf.cast(tensor_dict['num_detections'][0], tf.int32)
                detection_boxes = tf.slice(detection_boxes, [0, 0], [real_num_detection, -1])
                detection_masks = tf.slice(detection_masks, [0, 0, 0], [real_num_detection, -1, -1])
                detection_masks_reframed = utils_ops.reframe_box_masks_to_image_masks(
                        detection_masks, detection_boxes, image.shape[0], image.shape[1])
                detection_masks_reframed = tf.cast(
                        tf.greater(detection_masks_reframed, 0.5), tf.uint8)
                # Follow the convention by adding back the batch dimension
                tensor_dict['detection_masks'] = tf.expand_dims(
                        detection_masks_reframed, 0)

            image_tensor = tf.get_default_graph().get_tensor_by_name('image_tensor:0')

            # Run inference
            output_dict = self.sess.run(tensor_dict, feed_dict={image_tensor: np.expand_dims(image, 0)})

        # all outputs are float32 numpy arrays, so convert types as appropriate
        output_dict['num_detections'] = int(output_dict['num_detections'][0])
        output_dict['detection_classes'] = output_dict[
                'detection_classes'][0].astype(np.uint8)
        output_dict['detection_boxes'] = output_dict['detection_boxes'][0]
        output_dict['detection_scores'] = output_dict['detection_scores'][0]

        if 'detection_masks' in output_dict:
            output_dict['detection_masks'] = output_dict['detection_masks'][0]

        return output_dict


    def json_handler(self, image, output_dict):
        boxes = output_dict['detection_boxes']
        classes = output_dict['detection_classes']
        scores = output_dict['detection_scores']

        d = {}
        l = []
        for i, v in enumerate(scores):
            if v > 0:
                aux = {}
                aux['y0'] = float("{0:.4f}".format(boxes[i][0]))
                aux['x0'] = float("{0:.4f}".format(boxes[i][1]))
                aux['y1'] = float("{0:.4f}".format(boxes[i][2]))
                aux['x1'] = float("{0:.4f}".format(boxes[i][3]))
                aux['object'] = self.category_index[classes[i]]['name']
                aux['probability'] = float("{0:.4f}".format(scores[i]))
                l.append(aux)

        d['data'] = l
        return json.dumps(d)


    def image_handler(self, image, output_dict):
        vis_util.visualize_boxes_and_labels_on_image_array(
            image,
            output_dict['detection_boxes'],
            output_dict['detection_classes'],
            output_dict['detection_scores'],
            self.category_index,
            instance_masks=output_dict.get('detection_masks'),
            use_normalized_coordinates=True,
            line_thickness=4,
            min_score_thresh=.3)

        return image


    def run(self, image, handler=None):
        if handler is None:
            handler = self.json_handler
        return handler(image, self._run_inference(image))


if __name__ == "__main__":
    img_path = sys.argv[1] 
    img = np.asarray(Image.open(img_path), dtype=np.uint8)

    GRAPH_PATH = "./models/ssd_mobilenet_v1_coco_2017_11_17/frozen_inference_graph.pb"
    LABELS_PATH = "./models/ssd_mobilenet_v1_coco_2017_11_17/mscoco_label_map.pbtxt"
    NUM_CLASSES = 90

    model = ObjectDetector(GRAPH_PATH, LABELS_PATH, NUM_CLASSES)

    out = model.run(img.copy(), handler=model.image_handler)
    img = Image.fromarray(out)
    img.show()
