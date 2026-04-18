from flask_wtf import FlaskForm
from wtforms import HiddenField, PasswordField, StringField
from wtforms.validators import InputRequired, Optional, Regexp

NUMERIC_ID = Regexp(r"^\d+$", message="Only numbers are allowed.")


class CourseForm(FlaskForm):
    studentId = StringField("Student ID", validators=[InputRequired(), NUMERIC_ID])
    equipmentId1 = StringField("Equipment ID", validators=[InputRequired(), NUMERIC_ID])
    equipmentId2 = StringField("Equipment ID", validators=[Optional(), NUMERIC_ID])
    equipmentId3 = StringField("Equipment ID", validators=[Optional(), NUMERIC_ID])
    equipmentId4 = StringField("Equipment ID", validators=[Optional(), NUMERIC_ID])
    equipmentId5 = StringField("Equipment ID", validators=[Optional(), NUMERIC_ID])


class ReturnForm(FlaskForm):
    hStudentId = HiddenField(validators=[InputRequired(), NUMERIC_ID])
    hEquipmentId = HiddenField(validators=[InputRequired(), NUMERIC_ID])


class LoginForm(FlaskForm):
    password = PasswordField("Password", validators=[InputRequired()])
    next = HiddenField()
