from flask_wtf import FlaskForm
from wtforms import IntegerField, DateTimeField, FieldList, FormField
from wtforms.validators import InputRequired

class CourseForm(FlaskForm):
    studentId = IntegerField('Student ID', validators=[InputRequired()])
    equipmentId1 = IntegerField('Equipment ID', validators=[InputRequired()])
    equipmentId2 = IntegerField('Equipment ID')
    equipmentId3 = IntegerField('Equipment ID')
    equipmentId4 = IntegerField('Equipment ID')
    equipmentId5 = IntegerField('Equipment ID')