-- ============================================================================
-- Migration 002: Seed 53 Comprehensive Bilingual Achievements & Default Settings
-- Engine: Microsoft Azure SQL Database / SQL Server (T-SQL)
-- ============================================================================

MERGE achievements AS target
USING (VALUES
    ('FIRST_QUIZ', 'quiz_progress', N'First Quiz', N'أول اختبار', N'Completed your first quiz', N'أكملت أول اختبار لك بنجاح', N'🏅', 50, 'bronze', 1),
    ('QUIZZES_10', 'quiz_progress', N'10 Quizzes', N'10 اختبارات', N'Completed 10 quizzes', N'أكملت 10 اختبارات', N'📚', 100, 'bronze', 2),
    ('QUIZZES_50', 'quiz_progress', N'50 Quizzes', N'50 اختباراً', N'Completed 50 quizzes', N'أكملت 50 اختباراً', N'🎓', 300, 'silver', 3),
    ('QUIZZES_100', 'quiz_progress', N'100 Quizzes', N'100 اختبار', N'Completed 100 quizzes', N'أكملت 100 اختبار', N'👑', 750, 'gold', 4),
    ('QUESTIONS_1000', 'quiz_progress', N'1,000 Questions Answered', N'1,000 سؤال', N'Answered 1,000 questions in quizzes', N'أجبت على 1,000 سؤال في الاختبارات', N'🧠', 500, 'silver', 5),
    ('QUESTIONS_10000', 'quiz_progress', N'10,000 Questions Answered', N'10,000 سؤال', N'Answered 10,000 questions in quizzes', N'أجبت على 10,000 سؤال في الاختبارات', N'⚡', 2000, 'gold', 6),
    ('MODULE_MASTER', 'quiz_progress', N'Module Master', N'خبير الموديول', N'Completed all quizzes in a complete module', N'أكملت جميع اختبارات موديول كامل', N'🏆', 250, 'silver', 7),
    ('ALL_ROUNDER', 'quiz_progress', N'All-Rounder', N'شامل المعرفة', N'Completed quizzes across 5 different subjects/modules', N'أكملت اختبارات في 5 موديولات مختلفة', N'🌐', 400, 'gold', 8),
    ('CORRECT_10', 'accuracy', N'10 Correct Answers', N'10 إجابات صحيحة', N'Answered 10 questions correctly', N'أجبت على 10 أسئلة بشكل صحيح', N'🎯', 30, 'bronze', 9),
    ('CORRECT_100', 'accuracy', N'100 Correct Answers', N'100 إجابة صحيحة', N'Answered 100 questions correctly', N'أجبت على 100 سؤال بشكل صحيح', N'🎯', 150, 'bronze', 10),
    ('CORRECT_500', 'accuracy', N'500 Correct Answers', N'500 إجابة صحيحة', N'Answered 500 questions correctly', N'أجبت على 500 سؤال بشكل صحيح', N'🎯', 500, 'silver', 11),
    ('PERFECT_SCORE', 'accuracy', N'Perfect Score', N'درجة كاملة', N'Scored 100% on any quiz', N'حققت درجة كاملة 100% في أي اختبار', N'💯', 100, 'bronze', 12),
    ('TRIPLE_PERFECT', 'accuracy', N'Triple Perfect', N'ثلاثية كاملة', N'Scored 100% on 3 different quizzes', N'حققت 100% في 3 اختبارات مختلفة', N'⭐', 300, 'silver', 13),
    ('PERFECTIONIST', 'accuracy', N'Perfectionist', N'الباحث عن الكمال', N'Scored 100% on 10 different quizzes', N'حققت 100% في 10 اختبارات مختلفة', N'🌟', 800, 'gold', 14),
    ('ACCURACY_90', 'accuracy', N'90% Accuracy', N'دقة 90%', N'Maintained 90%+ overall accuracy over at least 10 quizzes', N'حافظت على دقة 90%+ عبر 10 اختبارات على الأقل', N'🏹', 400, 'silver', 15),
    ('FLAWLESS_RUN', 'accuracy', N'Flawless Run', N'مسيرة بلا أخطاء', N'Completed a 20+ question quiz with zero mistakes', N'أكملت اختباراً من 20 سؤالاً على الأقل بدون أي خطأ', N'💎', 500, 'gold', 16),
    ('STREAK_3', 'streaks', N'3 Correct in a Row', N'3 على التوالي', N'Answered 3 questions correctly in a row', N'3 إجابات صحيحة متتالية', N'🔥', 25, 'bronze', 17),
    ('STREAK_10', 'streaks', N'10 Streak', N'10 على التوالي', N'Got 10 correct answers in a row', N'10 إجابات صحيحة متتالية', N'🔥', 100, 'bronze', 18),
    ('STREAK_25', 'streaks', N'25 Correct in a Row', N'25 على التوالي', N'Got 25 correct answers in a row', N'25 إجابة صحيحة متتالية', N'🔥', 300, 'silver', 19),
    ('STREAK_50', 'streaks', N'50 Correct in a Row', N'50 على التوالي', N'Got 50 correct answers in a row', N'50 إجابة صحيحة متتالية', N'🌋', 750, 'gold', 20),
    ('STREAK_7_DAYS', 'streaks', N'7-Day Streak', N'شعلة 7 أيام', N'Studied on 7 consecutive days', N'واظبت على المذاكرة 7 أيام متتالية', N'📅', 250, 'silver', 21),
    ('STREAK_30_DAYS', 'streaks', N'30-Day Streak', N'شعلة الشهر', N'Studied on 30 consecutive days', N'واظبت على المذاكرة 30 يوماً متتالياً', N'🗓️', 1000, 'gold', 22),
    ('EARLY_BIRD', 'streaks', N'Early Bird', N'طائر الصباح', N'Completed a quiz between 5:00 AM and 8:00 AM', N'أكملت اختباراً بين الساعة 5:00 و 8:00 صباحاً', N'🌅', 75, 'bronze', 23),
    ('NIGHT_OWL', 'streaks', N'Night Owl', N'بومة الليل', N'Completed a quiz between 11:00 PM and 3:00 AM', N'أكملت اختباراً بين الساعة 11:00 مساءً و 3:00 فجراً', N'🦉', 75, 'bronze', 24),
    ('QUICK_THINKER', 'speed', N'Quick Thinker', N'سرعة بديهة', N'Answered a question correctly in under 5 seconds', N'إجابة صحيحة خلال أقل من 5 ثوانٍ', N'⏱️', 50, 'bronze', 25),
    ('LIGHTNING_BRAIN', 'speed', N'Lightning Brain', N'عقل برقي', N'Answered 5 questions in a row in under 5s each', N'5 إجابات صحيحة متتالية كل منها بأقل من 5 ثوانٍ', N'⚡', 200, 'silver', 26),
    ('SPEED_RUNNER', 'speed', N'Speed Runner', N'عداء الاختبارات', N'Finished a 10+ question quiz in under 2 minutes with 80%+ accuracy', N'إنهاء اختبار من 10+ أسئلة في أقل من دقيقتين بدقة 80%+', N'🏎️', 350, 'silver', 27),
    ('SPEED_CHAMPION', 'speed', N'Speed Champion', N'بطل السرعة', N'Achieved the fastest completion time on any quiz leaderboard', N'أسرع وقت إكمال على لوحة متصدري الاختبار', N'🏆', 600, 'gold', 28),
    ('XP_1000', 'xp_ranking', N'1,000 XP', N'1,000 خبرة', N'Earned 1,000 total XP', N'جمعت 1,000 نقطة خبرة', N'⭐', 100, 'bronze', 29),
    ('XP_10000', 'xp_ranking', N'10,000 XP', N'10,000 خبرة', N'Earned 10,000 total XP', N'جمعت 10,000 نقطة خبرة', N'🌟', 500, 'silver', 30),
    ('LEVEL_10', 'xp_ranking', N'Level 10', N'المستوى 10', N'Reached Student Level 10', N'وصلت إلى المستوى العاشر', N'🎖️', 300, 'silver', 31),
    ('TOP_100', 'xp_ranking', N'Top 100', N'أفضل 100', N'Reached Top 100 on the global leaderboard', N'وصلت إلى قائمة أفضل 100 طالب', N'🥉', 200, 'bronze', 32),
    ('TOP_10', 'xp_ranking', N'Top 10', N'أفضل 10', N'Reached Top 10 on the global leaderboard', N'وصلت إلى قائمة أفضل 10 طلاب متصدرين', N'🥈', 600, 'gold', 33),
    ('PODIUM_FINISH', 'xp_ranking', N'Podium Finish', N'منصة التتويج', N'Finished in the Top 3 in a quiz leaderboard', N'حققت أحد المراكز الثلاثة الأولى في اختبار', N'🥇', 300, 'silver', 34),
    ('THREE_TIME_CHAMPION', 'xp_ranking', N'Three-Time Champion', N'البطل الثلاثي', N'Won 1st place in 3 different quizzes', N'حققت المركز الأول في 3 اختبارات مختلفة', N'👑', 1000, 'gold', 35),
    ('FIRST_SHARE', 'special', N'First Share', N'أول مشاركة', N'Shared a quiz result with a study friend', N'شاركت نتيجة اختبارك مع زميل', N'🔗', 50, 'bronze', 36),
    ('STUDY_PARTNER', 'special', N'Study Partner', N'شريك الدراسة', N'Invited a classmate who completed a quiz', N'دعوت زميلاً دراسياً وأكمل اختباره الأول', N'👥', 150, 'bronze', 37),
    ('WELCOME_BACK', 'special', N'Welcome Back', N'عودة حميدة', N'Returned and completed a quiz after 7 days away', N'عدت للمذاكرة وأكملت اختباراً بعد انقطاع 7 أيام', N'🔄', 75, 'bronze', 38),
    ('NEVER_GIVE_UP', 'special', N'Never Give Up', N'لا استسلام', N'Retried a failed quiz (<50%) and scored >80%', N'أعدت اختباراً رسبت فيه وحققت أكثر من 80%', N'💪', 150, 'bronze', 39),
    ('REDEMPTION', 'special', N'Redemption', N'النهوض العظيم', N'Turned a 0% into a 100% perfect score on retry', N'حولت نسبة 0% إلى 100% كاملة في الإعادة', N'🦅', 300, 'silver', 40),
    ('STUDY_MARATHON', 'special', N'Study Marathon', N'ماراثون المذاكرة', N'Completed 5 quizzes in a single day', N'أكملت 5 اختبارات في يوم واحد', N'🏃', 250, 'silver', 41),
    ('LEGENDARY_STUDENT', 'special', N'Legendary Student', N'طالب أسطوري', N'Unlocked 25 total achievements', N'فتحت 25 إنجازاً مختلفاً', N'👑', 1000, 'gold', 42),
    ('ACHIEVEMENT_HUNTER', 'special', N'Achievement Hunter', N'صائد الإنجازات', N'Unlocked 40 total achievements', N'فتحت 40 إنجازاً مختلفاً', N'🎖️', 2000, 'gold', 43),
    ('ANATOMY_MASTER', 'medical', N'Anatomy Master', N'خبير التشريح', N'Completed 10 Anatomy quizzes with >80% accuracy', N'أكملت 10 اختبارات تشريح بدقة تفوق 80%', N'🫀', 350, 'silver', 44),
    ('PHYSIOLOGY_MASTER', 'medical', N'Physiology Master', N'خبير الفسيولوجي', N'Completed 10 Physiology quizzes with >80% accuracy', N'أكملت 10 اختبارات فسيولوجي بدقة تفوق 80%', N'⚡', 350, 'silver', 45),
    ('HISTOLOGY_MASTER', 'medical', N'Histology Master', N'خبير الهستولوجي', N'Completed 10 Histology quizzes with >80% accuracy', N'أكملت 10 اختبارات هستولوجي بدقة تفوق 80%', N'🔬', 350, 'silver', 46),
    ('BIOCHEMISTRY_MASTER', 'medical', N'Biochemistry Master', N'خبير الكيمياء الحيوية', N'Completed 10 Biochemistry quizzes with >80% accuracy', N'أكملت 10 اختبارات كيمياء حيوية بدقة تفوق 80%', N'🧪', 350, 'silver', 47),
    ('SYSTEMS_MASTER', 'medical', N'Systems Master', N'خبير أجهزة الجسم', N'Completed quizzes in 3 systemic modules', N'أكملت اختبارات في 3 موديولات طبية مختلفة', N'🏥', 500, 'gold', 48),
    ('EXAM_READY', 'medical', N'Exam Ready', N'جاهز للاختبار', N'Passed 5 comprehensive or mock final quizzes', N'اجتزت 5 اختبارات شاملة أو تجريبية نهائية', N'📋', 500, 'gold', 49),
    ('REVISION_HERO', 'medical', N'Revision Hero', N'بطل المراجعة', N'Reviewed and corrected 50 previously missed questions', N'راجعت وصححت 50 سؤالاً أخطأت بها سابقاً', N'🔁', 300, 'silver', 50),
    ('SPEED_DEMON', 'speed', N'Speed Demon', N'شيطان السرعة', N'Completed a quiz in record lightning time', N'أكملت اختباراً في زمن قياسي سريع جداً', N'⚡', 200, 'silver', 51),
    ('TOP_PLAYER', 'xp_ranking', N'Top 10 Player', N'متصدر المراكز الأولى', N'Consistently finished in the top ranks', N'حققت مراكز متقدمة في لوحة الشرف', N'🌟', 500, 'gold', 52),
    ('QUIZ_CHAMPION', 'xp_ranking', N'Quiz Champion', N'بطل الاختبارات', N'Earned the ultimate quiz championship honor', N'حصلت على لقب بطل الاختبارات العام', N'🏆', 500, 'gold', 53)
) AS source (code, category, title_en, title_ar, desc_en, desc_ar, icon, points, badge_color, sort_order)
ON target.code = source.code
WHEN MATCHED THEN
    UPDATE SET 
        target.category = source.category,
        target.title_en = source.title_en,
        target.title_ar = source.title_ar,
        target.desc_en = source.desc_en,
        target.desc_ar = source.desc_ar,
        target.icon = source.icon,
        target.points = source.points,
        target.badge_color = source.badge_color,
        target.sort_order = source.sort_order
WHEN NOT MATCHED THEN
    INSERT (code, category, title_en, title_ar, desc_en, desc_ar, icon, points, badge_color, sort_order)
    VALUES (source.code, source.category, source.title_en, source.title_ar, source.desc_en, source.desc_ar, source.icon, source.points, source.badge_color, source.sort_order);

-- Seed Default System Settings if not already present
MERGE system_settings AS target
USING (VALUES
    ('xp_per_correct_answer', '10'),
    ('xp_quiz_completion', '50'),
    ('xp_perfect_score_bonus', '100'),
    ('xp_streak_bonus', '25'),
    ('site_name', 'Unified Quiz Platform'),
    ('allow_guest_browsing', 'false')
) AS source (key_name, value)
ON target.key_name = source.key_name
WHEN NOT MATCHED THEN
    INSERT (key_name, value)
    VALUES (source.key_name, source.value);
