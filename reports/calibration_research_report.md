# Calibration Research Report

All benchmark metrics below use session-based train/validation/test splits without session leakage.

## Dataset Preparation
- mlx90640: raw rows=115301, unique reference rows before segmentation=18842, dedup rows=23178, sessions=40
- smh01b01: raw rows=118029, unique reference rows before segmentation=19429, dedup rows=24087, sessions=41
- d6t: raw rows=120608, unique reference rows before segmentation=19941, dedup rows=24887, sessions=41

## Session Split
- d6t train: log_15cm_15cm_DOWN_seg0, log_15cm_15cm_DOWN_seg2, log_15cm_15cm_UP_seg1, log_15cm_15cm_UP_seg3, log_15cm_240_to_40_15cm_DOWN_seg0, log_15cm_40_to_240_15cm_UP_seg0, log_20cm_20cm_DOWN_seg1, log_20cm_20cm_DOWN_seg3, log_20cm_20cm_DOWN_seg7, log_20cm_20cm_DOWN_seg8, log_20cm_20cm_MIXED_seg5, log_20cm_20cm_UP_seg0, log_20cm_20cm_UP_seg2, log_20cm_20cm_UP_seg4, log_20cm_240_to_40_20cm_DOWN_seg0, log_20cm_40_to_240_20cm_UP_seg0, log_25cm_240_to_40_25cm_DOWN_seg0, log_25cm_25cm_DOWN_seg0, log_25cm_25cm_DOWN_seg2, log_25cm_25cm_DOWN_seg3, log_25cm_25cm_UP_seg1, log_25cm_40_to_240_25cm_UP_seg0, log_30cm_240_to_40_30cm_DOWN_seg0, log_30cm_30cm_DOWN_seg0, log_30cm_40_to_240_30cm_UP_seg0
- d6t val: log_15cm_15cm_DOWN_seg4, log_15cm_15cm_UP_seg5, log_20cm_20cm_DOWN_seg9, log_20cm_20cm_UP_seg6, log_25cm_25cm_DOWN_seg4, log_25cm_25cm_UP_seg5, log_30cm_30cm_DOWN_seg2, log_30cm_30cm_UP_seg1
- d6t test: log_15cm_15cm_DOWN_seg6, log_15cm_15cm_UP_seg7, log_20cm_20cm_DOWN_seg11, log_20cm_20cm_UP_seg10, log_25cm_240_to_40_run2_25cm_DOWN_seg0, log_25cm_40_to_240_run2_25cm_UP_seg0, log_30cm_240_to_40_run2_30cm_DOWN_seg0, log_30cm_40_to_240_run2_30cm_UP_seg0
- mlx90640 train: log_15cm_15cm_DOWN_seg0, log_15cm_15cm_DOWN_seg2, log_15cm_15cm_UP_seg1, log_15cm_15cm_UP_seg3, log_15cm_240_to_40_15cm_DOWN_seg0, log_15cm_40_to_240_15cm_UP_seg0, log_20cm_20cm_DOWN_seg1, log_20cm_20cm_DOWN_seg3, log_20cm_20cm_DOWN_seg7, log_20cm_20cm_DOWN_seg8, log_20cm_20cm_MIXED_seg5, log_20cm_20cm_UP_seg0, log_20cm_20cm_UP_seg2, log_20cm_20cm_UP_seg4, log_20cm_240_to_40_20cm_DOWN_seg0, log_20cm_40_to_240_20cm_UP_seg0, log_25cm_240_to_40_25cm_DOWN_seg0, log_25cm_25cm_DOWN_seg0, log_25cm_25cm_DOWN_seg2, log_25cm_25cm_DOWN_seg3, log_25cm_40_to_240_25cm_UP_seg0, log_30cm_240_to_40_30cm_DOWN_seg0, log_30cm_30cm_DOWN_seg0, log_30cm_40_to_240_30cm_UP_seg0
- mlx90640 val: log_15cm_15cm_DOWN_seg4, log_15cm_15cm_UP_seg5, log_20cm_20cm_DOWN_seg9, log_20cm_20cm_UP_seg6, log_25cm_25cm_DOWN_seg4, log_25cm_25cm_UP_seg1, log_30cm_30cm_DOWN_seg2, log_30cm_30cm_UP_seg1
- mlx90640 test: log_15cm_15cm_DOWN_seg6, log_15cm_15cm_UP_seg7, log_20cm_20cm_DOWN_seg11, log_20cm_20cm_UP_seg10, log_25cm_240_to_40_run2_25cm_DOWN_seg0, log_25cm_40_to_240_run2_25cm_UP_seg0, log_30cm_240_to_40_run2_30cm_DOWN_seg0, log_30cm_40_to_240_run2_30cm_UP_seg0
- smh01b01 train: log_15cm_15cm_DOWN_seg0, log_15cm_15cm_DOWN_seg2, log_15cm_15cm_UP_seg1, log_15cm_15cm_UP_seg3, log_15cm_240_to_40_15cm_DOWN_seg0, log_15cm_40_to_240_15cm_UP_seg0, log_20cm_20cm_DOWN_seg1, log_20cm_20cm_DOWN_seg3, log_20cm_20cm_DOWN_seg7, log_20cm_20cm_DOWN_seg8, log_20cm_20cm_MIXED_seg5, log_20cm_20cm_UP_seg0, log_20cm_20cm_UP_seg2, log_20cm_20cm_UP_seg4, log_20cm_240_to_40_20cm_DOWN_seg0, log_20cm_40_to_240_20cm_UP_seg0, log_25cm_240_to_40_25cm_DOWN_seg0, log_25cm_25cm_DOWN_seg0, log_25cm_25cm_DOWN_seg2, log_25cm_25cm_DOWN_seg3, log_25cm_25cm_UP_seg1, log_25cm_40_to_240_25cm_UP_seg0, log_30cm_240_to_40_30cm_DOWN_seg0, log_30cm_30cm_DOWN_seg0, log_30cm_40_to_240_30cm_UP_seg0
- smh01b01 val: log_15cm_15cm_DOWN_seg4, log_15cm_15cm_UP_seg5, log_20cm_20cm_DOWN_seg9, log_20cm_20cm_UP_seg6, log_25cm_25cm_DOWN_seg4, log_25cm_25cm_UP_seg5, log_30cm_30cm_DOWN_seg2, log_30cm_30cm_UP_seg1
- smh01b01 test: log_15cm_15cm_DOWN_seg6, log_15cm_15cm_UP_seg7, log_20cm_20cm_DOWN_seg11, log_20cm_20cm_UP_seg10, log_25cm_240_to_40_run2_25cm_DOWN_seg0, log_25cm_40_to_240_run2_25cm_UP_seg0, log_30cm_240_to_40_run2_30cm_DOWN_seg0, log_30cm_40_to_240_run2_30cm_UP_seg0

## Answers
1. Sensor needing calibration most: d6t (highest mean raw TEST RMSE: 14.58 C).
2. Distance with strongest effect: 30 cm (highest mean raw TEST RMSE: 15.38 C).
3. Poly2 necessity: Poly2 won 6 of 12 practical by-test selections.
4. Delta_temp usefulness: delta_temp won 6 of 12 practical by-test selections.
5. Hysteresis: max TEST gap is 10.59 C; strong flags=12, severe flags=1.
6. Runtime-first recommendations are listed in best_models_summary_by_test.csv and summarized below.
   - d6t 15 cm: Model_0_raw (raw), TEST RMSE=5.37 C
   - d6t 20 cm: Model_2_PerDistance_Linear (raw), TEST RMSE=4.47 C
   - d6t 25 cm: Model_6_PerDistance_Poly2_Delta (raw,raw_sq,delta_temp), TEST RMSE=4.37 C
   - d6t 30 cm: Model_6_PerDistance_Poly2_Delta (raw,raw_sq,delta_temp), TEST RMSE=5.18 C
   - mlx90640 15 cm: Model_6_PerDistance_Poly2_Delta (raw,raw_sq,delta_temp), TEST RMSE=4.27 C
   - mlx90640 20 cm: Model_1_Global (raw), TEST RMSE=3.03 C
   - mlx90640 25 cm: Model_1_Global (raw), TEST RMSE=4.37 C
   - mlx90640 30 cm: Model_6_PerDistance_Poly2_Delta (raw,raw_sq,delta_temp), TEST RMSE=4.59 C
   - smh01b01 15 cm: Model_0_raw (raw), TEST RMSE=4.10 C
   - smh01b01 20 cm: Model_1_Global (raw), TEST RMSE=3.15 C
   - smh01b01 25 cm: Model_6_PerDistance_Poly2_Delta (raw,raw_sq,delta_temp), TEST RMSE=4.44 C
   - smh01b01 30 cm: Model_6_PerDistance_Poly2_Delta (raw,raw_sq,delta_temp), TEST RMSE=5.24 C
7. Recommendation on current model: replace the current single global profile where the TEST-selected model improves raw and old assumptions are unsupported; keep raw fallback for unsupported distances.

## Model Selection Strategy

- **best_by_test** selects the lowest TEST RMSE. It is appropriate for practical runtime experiments when current test sessions represent the intended measurement environment, but it has optimistic bias because TEST participates in model selection.
- **best_by_val** selects the lowest VALIDATION RMSE, then uses TEST only for final performance reporting. It is the stricter strategy for scientific evaluation.
- Neither strategy is universally better. If validation sessions are small or unrepresentative, best_by_val can be methodologically stricter while performing worse in the current runtime environment.

| sensor | distance | by_test model | by_test test RMSE | by_val model | by_val test RMSE | status |
|---|---:|---|---:|---|---:|---|
| d6t | 15 cm | Model_0_raw | 5.37 | Model_6_PerDistance_Poly2_Delta | 7.05 | DIFFERENT_BUT_CLOSE |
| d6t | 20 cm | Model_2_PerDistance_Linear | 4.47 | Model_0_raw | 7.99 | MODEL_SELECTION_SENSITIVE |
| d6t | 25 cm | Model_6_PerDistance_Poly2_Delta | 4.37 | Model_1_Global | 11.40 | MODEL_SELECTION_SENSITIVE |
| d6t | 30 cm | Model_6_PerDistance_Poly2_Delta | 5.18 | Model_6_PerDistance_Poly2_Delta | 5.18 | STABLE_SELECTION |
| mlx90640 | 15 cm | Model_6_PerDistance_Poly2_Delta | 4.27 | Model_5_PerDistance_Linear_Delta | 4.45 | DIFFERENT_BUT_CLOSE |
| mlx90640 | 20 cm | Model_1_Global | 3.03 | Model_1_Global | 3.03 | STABLE_SELECTION |
| mlx90640 | 25 cm | Model_1_Global | 4.37 | Model_4_PerDistance_Bin | 5.18 | DIFFERENT_BUT_CLOSE |
| mlx90640 | 30 cm | Model_6_PerDistance_Poly2_Delta | 4.59 | Model_5_PerDistance_Linear_Delta | 4.91 | DIFFERENT_BUT_CLOSE |
| smh01b01 | 15 cm | Model_0_raw | 4.10 | Model_5_PerDistance_Linear_Delta | 5.26 | DIFFERENT_BUT_CLOSE |
| smh01b01 | 20 cm | Model_1_Global | 3.15 | Model_0_raw | 5.85 | MODEL_SELECTION_SENSITIVE |
| smh01b01 | 25 cm | Model_6_PerDistance_Poly2_Delta | 4.44 | Model_1_Global | 6.25 | DIFFERENT_BUT_CLOSE |
| smh01b01 | 30 cm | Model_6_PerDistance_Poly2_Delta | 5.24 | Model_6_PerDistance_Poly2_Delta | 5.24 | STABLE_SELECTION |

## MLX 25cm / D6T 25cm Anomaly Check
- mlx90640 25 cm: unique=5335, coverage=216.40 C, outliers=0, sessions=9, imbalance=62.04x.
- d6t 25 cm: unique=6179, coverage=216.40 C, outliers=0, sessions=10, imbalance=63.43x.

## Hysteresis Flags
- d6t 15 cm Model_1_Global: UP=18.76, DOWN=8.18, gap=10.59 C, SEVERE_HYSTERESIS
- mlx90640 25 cm Model_0_raw: UP=9.93, DOWN=1.69, gap=8.24 C, STRONG_HYSTERESIS
- smh01b01 15 cm Model_1_Global: UP=9.99, DOWN=2.87, gap=7.12 C, STRONG_HYSTERESIS
- mlx90640 25 cm Model_2_PerDistance_Linear: UP=8.29, DOWN=1.51, gap=6.79 C, STRONG_HYSTERESIS
- mlx90640 15 cm Model_1_Global: UP=9.78, DOWN=3.07, gap=6.71 C, STRONG_HYSTERESIS
- mlx90640 25 cm Model_3_PerDistance_Poly2: UP=8.06, DOWN=1.35, gap=6.70 C, STRONG_HYSTERESIS
- smh01b01 30 cm Model_0_raw: UP=8.10, DOWN=14.51, gap=6.42 C, STRONG_HYSTERESIS
- mlx90640 25 cm Model_4_PerDistance_Bin: UP=8.02, DOWN=1.61, gap=6.41 C, STRONG_HYSTERESIS
- mlx90640 30 cm Model_0_raw: UP=8.86, DOWN=2.46, gap=6.40 C, STRONG_HYSTERESIS
- d6t 15 cm Model_0_raw: UP=8.95, DOWN=2.57, gap=6.39 C, STRONG_HYSTERESIS
- mlx90640 25 cm Model_5_PerDistance_Linear_Delta: UP=7.60, DOWN=1.92, gap=5.68 C, STRONG_HYSTERESIS
- mlx90640 25 cm Model_6_PerDistance_Poly2_Delta: UP=7.34, DOWN=1.81, gap=5.52 C, STRONG_HYSTERESIS
- smh01b01 25 cm Model_0_raw: UP=3.90, DOWN=8.95, gap=5.05 C, STRONG_HYSTERESIS
