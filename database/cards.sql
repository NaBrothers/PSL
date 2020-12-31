create table IF NOT EXISTS `cards` (
  `ID` int(11) NOT NULL auto_increment,
  `Player` int(11) NOT NULL,
  `User` bigint Not Null,
  `Star` int(11) NOT NULL,
  `Style` VARCHAR(20) NOT NULL,
  primary key(`id`)
) default charset = utf8;
