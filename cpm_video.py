# For single hand and no body part in the picture
# ======================================================

import tensorflow as tf
from models.nets import cpm_hand_slim
import numpy as np
from utils import cpm_utils
import cv2
import time
import math
import sys

#yolo stuff
from darkflow.net.build import TFNet
import matplotlib.pyplot as plt


"""Parameters
"""
FLAGS = tf.app.flags.FLAGS
tf.app.flags.DEFINE_string('DEMO_TYPE',
                           default_value='SINGLE',
                           # default_value='SINGLE',
                           docstring='MULTI: show multiple stage,'
                                     'SINGLE: only last stage,'
                                     'HM: show last stage heatmap,'
                                     'paths to .jpg or .png image')
tf.app.flags.DEFINE_string('model_path',
                           default_value='models/weights/cpm_hand.pkl',
                           docstring='Your model')
tf.app.flags.DEFINE_integer('input_size',
                            default_value=368,
                            docstring='Input image size')
tf.app.flags.DEFINE_integer('hmap_size',
                            default_value=46,
                            docstring='Output heatmap size')
tf.app.flags.DEFINE_integer('cmap_radius',
                            default_value=21,
                            docstring='Center map gaussian variance')
tf.app.flags.DEFINE_integer('joints',
                            default_value=21,
                            docstring='Number of joints')
tf.app.flags.DEFINE_integer('stages',
                            default_value=6,
                            docstring='How many CPM stages')
#TODO: change default value to 0 later
"""
tf.app.flags.DEFINE_integer('cam_num',
                            default_value=0,
                            docstring='Webcam device number')
"""
tf.app.flags.DEFINE_string('cam_num',
                            default_value='test_imgs/21.avi',
                            docstring='Webcam device number')
tf.app.flags.DEFINE_bool('KALMAN_ON',
                         default_value=True,
                         docstring='enalbe kalman filter')
tf.app.flags.DEFINE_float('kalman_noise',
                            default_value=3e-2,
                            docstring='Kalman filter noise value')
tf.app.flags.DEFINE_string('color_channel',
                           default_value='RGB',
                           docstring='')

# Set color for each finger
joint_color_code = [[139, 53, 255],
                    [0, 56, 255],
                    [43, 140, 237],
                    [37, 168, 36],
                    [147, 147, 0],
                    [70, 17, 145]]


limbs = [[0, 1],
         [1, 2],
         [2, 3],
         [3, 4],
         [0, 5],
         [5, 6],
         [6, 7],
         [7, 8],
         [0, 9],
         [9, 10],
         [10, 11],
         [11, 12],
         [0, 13],
         [13, 14],
         [14, 15],
         [15, 16],
         [0, 17],
         [17, 18],
         [18, 19],
         [19, 20]
         ]
    
    
options = {
    'model': 'cfg/tiny-yolo-voc-2c.cfg',
    'load': 19125,
    'threshold': 0.05,
    #'gpu': 0.8
}

tfnet = TFNet(options)    


def main(argv):
    tf_device = '/gpu:0'
    with tf.device(tf_device):
        """Build graph
        """
        if FLAGS.color_channel == 'RGB':
            input_data = tf.placeholder(dtype=tf.float32, shape=[None, FLAGS.input_size, FLAGS.input_size, 3],
                                        name='input_image')
        else:
            input_data = tf.placeholder(dtype=tf.float32, shape=[None, FLAGS.input_size, FLAGS.input_size, 1],
                                        name='input_image')

        center_map = tf.placeholder(dtype=tf.float32, shape=[None, FLAGS.input_size, FLAGS.input_size, 1],
                                    name='center_map')

        model = cpm_hand_slim.CPM_Model(FLAGS.stages, FLAGS.joints + 1)
        model.build_model(input_data, center_map, 1)

    saver = tf.train.Saver()

    """Create session and restore weights
    """
    sess = tf.Session()

    sess.run(tf.global_variables_initializer())
    if FLAGS.model_path.endswith('pkl'):
        model.load_weights_from_file(FLAGS.model_path, sess, False)
    else:
        saver.restore(sess, FLAGS.model_path)

    test_center_map = cpm_utils.gaussian_img(FLAGS.input_size, FLAGS.input_size, FLAGS.input_size / 2,
                                             FLAGS.input_size / 2,
                                             FLAGS.cmap_radius)
    test_center_map = np.reshape(test_center_map, [1, FLAGS.input_size, FLAGS.input_size, 1])

    # Check weights
    for variable in tf.trainable_variables():
        with tf.variable_scope('', reuse=True):
            var = tf.get_variable(variable.name.split(':0')[0])
            print(variable.name, np.mean(sess.run(var)))

    if not FLAGS.DEMO_TYPE.endswith(('png', 'jpg')):
        #if not FLAGS.DEMO_TYPE.endswith(('avi', 'mp4')):
        cam = cv2.VideoCapture(FLAGS.cam_num)
    # Create kalman filters
    if FLAGS.KALMAN_ON:
        kalman_filter_array = [cv2.KalmanFilter(4, 2) for _ in range(FLAGS.joints)]
        for _, joint_kalman_filter in enumerate(kalman_filter_array):
            joint_kalman_filter.transitionMatrix = np.array([[1, 0, 1, 0], [0, 1, 0, 1], [0, 0, 1, 0], [0, 0, 0, 1]],
                                                            np.float32)
            joint_kalman_filter.measurementMatrix = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], np.float32)
            joint_kalman_filter.processNoiseCov = np.array([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
                                                           np.float32) * FLAGS.kalman_noise
    else:
        kalman_filter_array = None
	
    fourcc = cv2.VideoWriter_fourcc(*'XVID')
    out = cv2.VideoWriter('output.avi',fourcc, 20.0, (640,480))
    
    with tf.device(tf_device):

        while True:
            t1 = time.time()
            if FLAGS.DEMO_TYPE.endswith(('png', 'jpg')):
                test_img = cpm_utils.read_image(FLAGS.DEMO_TYPE, [], FLAGS.input_size, 'IMAGE')
            else:
                test_img = cpm_utils.read_image([], cam, FLAGS.input_size, 'WEBCAM')
                
            #yolo stuff 
            result = tfnet.return_predict(test_img) 

            count = 0
            hand1, hand2 = [], []
            if not result:
                pass
            else:
                for i in range(0, len(result)):
                    if (result[i]['label'] == 'hand_l') & (count == 0):
                        hand1 = [result[i]['topleft'], result[i]['bottomright']]
                        count+=1
                    elif (result[i]['label'] == 'hand_r') & (count == 1):
                        hand2 = [result[i]['topleft'], result[i]['bottomright']]
                        count+=1
                    #elif (count==1):
                       # hand2 = []
                    #elif (count==0):
                      #  hand1 = ['NA']
                      #  hand2 = ['NA']
                    #cropped image
                    if not hand1:
                         pass
                    else:
                        h1_image = test_img[hand1[0]['y']-10:hand1[1]['y']+10, hand1[0]['x']-10:hand1[1]['x']+10]
                        h1_image_resize = cv2.resize(h1_image, (FLAGS.input_size, FLAGS.input_size))
                        h1_img_input = h1_image_resize / 256.0 - 0.5
                        h1_img_input = np.expand_dims(h1_img_input, axis=0)
                        stage_heatmap_np_1 = sess.run([model.stage_heatmap[5]],
                                            feed_dict={'input_image:0': h1_img_input,
                                                       'center_map:0': test_center_map})
                        demo_img_1 = visualize_result(h1_image, FLAGS, stage_heatmap_np_1, kalman_filter_array)
                        test_img[hand1[0]['y']-10:hand1[1]['y']+10, hand1[0]['x']-10:hand1[1]['x']+10] = demo_img_1
                        test_img = cv2.rectangle(test_img, (hand1[0]['x']-10, hand1[0]['y']+10),(hand1[1]['x']-10, hand1[1]['y']+10), (255,0,0), 2)
                    if not hand2:
                        pass
                    else:
                        h2_image = test_img[hand2[0]['y']-10:hand2[1]['y']+10, hand2[0]['x']-10:hand2[1]['x']+10]
                        h2_image_resize = cv2.resize(h2_image, (FLAGS.input_size, FLAGS.input_size))
                        h2_img_input = h2_image_resize / 256.0 - 0.5
                        h2_img_input = np.expand_dims(h2_img_input, axis=0)
                        stage_heatmap_np_2 = sess.run([model.stage_heatmap[5]],
                                            feed_dict={'input_image:0': h2_img_input,
                                                       'center_map:0': test_center_map})
                        demo_img_2 = visualize_result(h2_image, FLAGS, stage_heatmap_np_2, kalman_filter_array)
                        test_img[hand2[0]['y']-10:hand2[1]['y']+10, hand2[0]['x']-10:hand2[1]['x']+10] = demo_img_2
                        test_img = cv2.rectangle(test_img, (hand2[0]['x']-10, hand2[0]['y']+10),(hand2[1]['x']-10, hand2[1]['y']+10), (255,0,255), 2)
                  
            
            if FLAGS.DEMO_TYPE.endswith(('png', 'jpg')):
                # Inference
                t1 = time.time()
                predict_heatmap, stage_heatmap_np = sess.run([model.current_heatmap,
                                                              model.stage_heatmap,
                                                              ],
                                                             feed_dict={'input_image:0': test_img_input,
                                                                        'center_map:0': test_center_map})

                # Show visualized image
                demo_img = visualize_result(test_img, FLAGS, stage_heatmap_np, kalman_filter_array)
                cv2.imshow('demo_img', demo_img.astype(np.uint8))
                if cv2.waitKey(0) == ord('q'): break
                print('fps: %.2f' % (1 / (time.time() - t1)))
            elif FLAGS.DEMO_TYPE == 'MULTI':

                # Inference
                t1 = time.time()
                predict_heatmap, stage_heatmap_np = sess.run([model.current_heatmap,
                                                              model.stage_heatmap,
                                                              ],
                                                             feed_dict={'input_image:0': test_img_input,
                                                                        'center_map:0': test_center_map})

                # Show visualized image
                demo_img = visualize_result(test_img, FLAGS, stage_heatmap_np, kalman_filter_array)
                cv2.imshow('demo_img', demo_img.astype(np.uint8))
                if cv2.waitKey(1) == ord('q'): break
                print('fps: %.2f' % (1 / (time.time() - t1)))


            elif FLAGS.DEMO_TYPE == 'SINGLE':

                # Inference
                t1 = time.time()

                # Show visualized image
                
                out.write((test_img).astype(np.uint8))
                # X2 times till here -concatenate here
                cv2.imshow('current heatmap', (test_img).astype(np.uint8))
                if cv2.waitKey(1) == ord('q'): break
                print('fps: %.2f' % (1 / (time.time() - t1)))


            elif FLAGS.DEMO_TYPE == 'HM':

                # Inference
                t1 = time.time()
                stage_heatmap_np = sess.run([model.stage_heatmap[FLAGS.stages - 1]],
                                            feed_dict={'input_image:0': test_img_input,
                                                       'center_map:0': test_center_map})
                print('fps: %.2f' % (1 / (time.time() - t1)))

                demo_stage_heatmap = stage_heatmap_np[len(stage_heatmap_np) - 1][0, :, :, 0:FLAGS.joints].reshape(
                    (FLAGS.hmap_size, FLAGS.hmap_size, FLAGS.joints))
                demo_stage_heatmap = cv2.resize(demo_stage_heatmap, (FLAGS.input_size, FLAGS.input_size))

                vertical_imgs = []
                tmp_img = None
                joint_coord_set = np.zeros((FLAGS.joints, 2))

                for joint_num in range(FLAGS.joints):
                    # Concat until 4 img
                    if (joint_num % 4) == 0 and joint_num != 0:
                        vertical_imgs.append(tmp_img)
                        tmp_img = None

                    demo_stage_heatmap[:, :, joint_num] *= (255 / np.max(demo_stage_heatmap[:, :, joint_num]))

                    # Plot color joints
                    if np.min(demo_stage_heatmap[:, :, joint_num]) > -50:
                        joint_coord = np.unravel_index(np.argmax(demo_stage_heatmap[:, :, joint_num]),
                                                       (FLAGS.input_size, FLAGS.input_size))
                        joint_coord_set[joint_num, :] = joint_coord
                        color_code_num = (joint_num // 4)

                        if joint_num in [0, 4, 8, 12, 16]:
                            joint_color = list(map(lambda x: x + 35 * (joint_num % 4), joint_color_code[color_code_num]))

                            cv2.circle(test_img, center=(joint_coord[1], joint_coord[0]), radius=3, color=joint_color,
                                       thickness=-1)
                        else:
                            joint_color = list(map(lambda x: x + 35 * (joint_num % 4), joint_color_code[color_code_num]))

                            cv2.circle(test_img, center=(joint_coord[1], joint_coord[0]), radius=3, color=joint_color,
                                       thickness=-1)

                    # Put text
                    tmp = demo_stage_heatmap[:, :, joint_num].astype(np.uint8)
                    tmp = cv2.putText(tmp, 'Min:' + str(np.min(demo_stage_heatmap[:, :, joint_num])),
                                      org=(5, 20), fontFace=cv2.FONT_HERSHEY_COMPLEX, fontScale=0.3, color=150)
                    tmp = cv2.putText(tmp, 'Mean:' + str(np.mean(demo_stage_heatmap[:, :, joint_num])),
                                      org=(5, 30), fontFace=cv2.FONT_HERSHEY_COMPLEX, fontScale=0.3, color=150)
                    tmp_img = np.concatenate((tmp_img, tmp), axis=0) \
                        if tmp_img is not None else tmp

                # Plot limbs
                for limb_num in range(len(limbs)):
                    if np.min(demo_stage_heatmap[:, :, limbs[limb_num][0]]) > -2000 and np.min(
                            demo_stage_heatmap[:, :, limbs[limb_num][1]]) > -2000:
                        x1 = joint_coord_set[limbs[limb_num][0], 0]
                        y1 = joint_coord_set[limbs[limb_num][0], 1]
                        x2 = joint_coord_set[limbs[limb_num][1], 0]
                        y2 = joint_coord_set[limbs[limb_num][1], 1]
                        length = ((x1 - x2) ** 2 + (y1 - y2) ** 2) ** 0.5
                        if length < 10000 and length > 5:
                            deg = math.degrees(math.atan2(x1 - x2, y1 - y2))
                            polygon = cv2.ellipse2Poly((int((y1 + y2) / 2), int((x1 + x2) / 2)),
                                                       (int(length / 2), 3),
                                                       int(deg),
                                                       0, 360, 1)
                            color_code_num = limb_num // 4
                            limb_color = list(map(lambda x: x + 35 * (limb_num % 4), joint_color_code[color_code_num]))

                            cv2.fillConvexPoly(test_img, polygon, color=limb_color)

                if tmp_img is not None:
                    tmp_img = np.lib.pad(tmp_img, ((0, vertical_imgs[0].shape[0] - tmp_img.shape[0]), (0, 0)),
                                         'constant', constant_values=(0, 0))
                    vertical_imgs.append(tmp_img)

                # Concat horizontally
                output_img = None
                for col in range(len(vertical_imgs)):
                    output_img = np.concatenate((output_img, vertical_imgs[col]), axis=1) if output_img is not None else \
                        vertical_imgs[col]

                output_img = output_img.astype(np.uint8)
                output_img = cv2.applyColorMap(output_img, cv2.COLORMAP_JET)
                test_img = cv2.resize(test_img, (300, 300), cv2.INTER_LANCZOS4)
                cv2.imshow('hm', output_img)
                cv2.moveWindow('hm', 2000, 200)
                cv2.imshow('rgb', test_img)
                cv2.moveWindow('rgb', 2000, 750)
                if cv2.waitKey(1) == ord('q'): break
        out.release()


def visualize_result(test_img, FLAGS, stage_heatmap_np, kalman_filter_array):
    t1 = time.time()
    demo_stage_heatmaps = []
    if FLAGS.DEMO_TYPE == 'MULTI':
        for stage in range(len(stage_heatmap_np)):
            demo_stage_heatmap = stage_heatmap_np[stage][0, :, :, 0:FLAGS.joints].reshape(
                (FLAGS.hmap_size, FLAGS.hmap_size, FLAGS.joints))
            demo_stage_heatmap = cv2.resize(demo_stage_heatmap, (test_img.shape[1], test_img.shape[0]))
            demo_stage_heatmap = np.amax(demo_stage_heatmap, axis=2)
            demo_stage_heatmap = np.reshape(demo_stage_heatmap, (test_img.shape[1], test_img.shape[0], 1))
            demo_stage_heatmap = np.repeat(demo_stage_heatmap, 3, axis=2)
            demo_stage_heatmap *= 255
            demo_stage_heatmaps.append(demo_stage_heatmap)

        last_heatmap = stage_heatmap_np[len(stage_heatmap_np) - 1][0, :, :, 0:FLAGS.joints].reshape(
            (FLAGS.hmap_size, FLAGS.hmap_size, FLAGS.joints))
        last_heatmap = cv2.resize(last_heatmap, (test_img.shape[1], test_img.shape[0]))
    else:
        last_heatmap = stage_heatmap_np[len(stage_heatmap_np) - 1][0, :, :, 0:FLAGS.joints].reshape(
            (FLAGS.hmap_size, FLAGS.hmap_size, FLAGS.joints))
        last_heatmap = cv2.resize(last_heatmap, (test_img.shape[1], test_img.shape[0]))
    print('hm resize time %f' % (time.time() - t1))

    t1 = time.time()
    joint_coord_set = np.zeros((FLAGS.joints, 2))

    # Plot joint colors
    if kalman_filter_array is not None:
        for joint_num in range(FLAGS.joints):
            joint_coord = np.unravel_index(np.argmax(last_heatmap[:, :, joint_num]),
                                           (test_img.shape[0], test_img.shape[1]))
            joint_coord = np.array(joint_coord).reshape((2, 1)).astype(np.float32)
            kalman_filter_array[joint_num].correct(joint_coord)
            kalman_pred = kalman_filter_array[joint_num].predict()
            joint_coord_set[joint_num, :] = np.array([kalman_pred[0], kalman_pred[1]]).reshape((2))

            color_code_num = (joint_num // 4)
            if joint_num in [0, 4, 8, 12, 16]:
                joint_color = list(map(lambda x: x + 35 * (joint_num % 4), joint_color_code[color_code_num]))

                cv2.circle(test_img, center=(joint_coord[1], joint_coord[0]), radius=3, color=joint_color, thickness=-1)
            else:
                joint_color = list(map(lambda x: x + 35 * (joint_num % 4), joint_color_code[color_code_num]))

                cv2.circle(test_img, center=(joint_coord[1], joint_coord[0]), radius=3, color=joint_color, thickness=-1)
    else:
        for joint_num in range(FLAGS.joints):
            joint_coord = np.unravel_index(np.argmax(last_heatmap[:, :, joint_num]),
                                           (test_img.shape[0], test_img.shape[1]))
            joint_coord_set[joint_num, :] = [joint_coord[0], joint_coord[1]]

            color_code_num = (joint_num // 4)
            if joint_num in [0, 4, 8, 12, 16]:
                joint_color = list(map(lambda x: x + 35 * (joint_num % 4), joint_color_code[color_code_num]))

                cv2.circle(test_img, center=(joint_coord[1], joint_coord[0]), radius=3, color=joint_color, thickness=-1)
            else:
                joint_color = list(map(lambda x: x + 35 * (joint_num % 4), joint_color_code[color_code_num]))

                cv2.circle(test_img, center=(joint_coord[1], joint_coord[0]), radius=3, color=joint_color, thickness=-1)
    print('plot joint time %f' % (time.time() - t1))

    t1 = time.time()
    # Plot limb colors
    for limb_num in range(len(limbs)):

        x1 = joint_coord_set[limbs[limb_num][0], 0]
        y1 = joint_coord_set[limbs[limb_num][0], 1]
        x2 = joint_coord_set[limbs[limb_num][1], 0]
        y2 = joint_coord_set[limbs[limb_num][1], 1]
        length = ((x1 - x2) ** 2 + (y1 - y2) ** 2) ** 0.5
        if length < 150 and length > 5:
            deg = math.degrees(math.atan2(x1 - x2, y1 - y2))
            polygon = cv2.ellipse2Poly((int((y1 + y2) / 2), int((x1 + x2) / 2)),
                                       (int(length / 2), 3),
                                       int(deg),
                                       0, 360, 1)
            color_code_num = limb_num // 4
            limb_color = list(map(lambda x: x + 35 * (limb_num % 4), joint_color_code[color_code_num]))

            cv2.fillConvexPoly(test_img, polygon, color=limb_color)
    print('plot limb time %f' % (time.time() - t1))

    if FLAGS.DEMO_TYPE == 'MULTI':
        upper_img = np.concatenate((demo_stage_heatmaps[0], demo_stage_heatmaps[1], demo_stage_heatmaps[2]), axis=1)
        lower_img = np.concatenate((demo_stage_heatmaps[3], demo_stage_heatmaps[len(stage_heatmap_np) - 1], test_img),
                                   axis=1)
        demo_img = np.concatenate((upper_img, lower_img), axis=0)
        return demo_img
    else:
        return test_img


if __name__ == '__main__':
    tf.app.run()
